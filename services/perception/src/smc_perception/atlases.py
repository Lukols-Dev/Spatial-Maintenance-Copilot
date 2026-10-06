"""Atlases in data/atlas/, and building one from a view set.

A build runs the code tools/build_atlas.py runs, in the same order and with
the same seeds, so the service and the CLI make the same atlas from the same
files. The service also writes <asset_id>.report.json, the numbers the CLI
prints.
"""

import os
import threading
from pathlib import Path

import cv2 as cv
import numpy as np
from pydantic import ValidationError
from smc_core.atlas_build import AtlasReport, build_atlas
from smc_core.board_pose import ViewPose, pose_views
from smc_core.calibration import Intrinsics, create_board
from smc_core.contracts import Atlas, Clicks, Vec3
from smc_core.images import read_images

from smc_perception.cameras import find_intrinsics
from smc_perception.errors import Conflict, Invalid, NotFound, WorkspaceError, describe
from smc_perception.image_headers import read_header
from smc_perception.models import (
    AtlasBuildReport,
    AtlasBuildRequest,
    AtlasDetail,
    AtlasPoint,
    AtlasSummary,
    PosedView,
)
from smc_perception.rig_file import measured_board
from smc_perception.view_sets import load_clicks
from smc_perception.workspace import (
    REPORT_SUFFIX,
    WorkspaceFiles,
    changed_at,
    modified_at,
    now,
    write_atomic,
)

# An atlas and its report are replaced together, one build at a time.
_lock = threading.Lock()


# ---- reading -----------------------------------------------------------------


def list_atlases(workspace: WorkspaceFiles) -> list[AtlasSummary]:
    return [summarise(workspace, asset_id) for asset_id in workspace.atlas_ids()]


def summarise(workspace: WorkspaceFiles, asset_id: str) -> AtlasSummary:
    """The atlas in one file; a file that is not an atlas is listed with its error."""
    path = workspace.atlas_dir / f"{asset_id}.json"
    try:
        atlas = _load(workspace, path)
        report = _report_of(workspace, asset_id, atlas)
        built_at = report.built_at if report is not None else modified_at(path)
    except (Invalid, OSError) as error:
        return AtlasSummary(
            asset_id=asset_id,
            file=path.name,
            version=None,
            frame=None,
            landmarks=None,
            target_id=None,
            target_sigma_mm=None,
            built_at=changed_at(path),
            has_report=False,
            error=str(error) if isinstance(error, Invalid) else "cannot read the file",
        )
    return AtlasSummary(
        asset_id=asset_id,
        file=path.name,
        version=atlas.version,
        frame=atlas.frame,
        landmarks=len(atlas.landmarks),
        target_id=atlas.target.id,
        target_sigma_mm=atlas.target.sigma_mm,
        built_at=built_at,
        has_report=report is not None,
        error=None,
    )


def read_atlas(workspace: WorkspaceFiles, asset_id: str) -> AtlasDetail:
    path = workspace.atlas_file(asset_id)
    if not path.is_file():
        raise NotFound(f"no atlas {asset_id!r}")
    try:
        atlas = _load(workspace, path)
    except Invalid as error:
        raise Conflict(str(error)) from error
    return AtlasDetail(atlas=atlas, report=_report_of(workspace, asset_id, atlas))


def _load(workspace: WorkspaceFiles, path: Path) -> Atlas:
    try:
        return Atlas.model_validate_json(path.read_bytes())
    except OSError as error:
        raise Invalid(f"cannot read {workspace.relative(path)}") from error
    except ValidationError as error:
        raise Invalid(f"{workspace.relative(path)} is not an atlas: {describe(error)}") from error


def _report_of(workspace: WorkspaceFiles, asset_id: str, atlas: Atlas) -> AtlasBuildReport | None:
    """The build report beside the atlas, if it describes this atlas.

    The CLI writes the atlas alone. Once it rebuilds an atlas the service
    built, the report beside it is of the earlier build; its points no longer
    sit where the atlas has them, and it is left out.
    """
    try:
        report = AtlasBuildReport.model_validate_json(workspace.report_file(asset_id).read_bytes())
    except OSError, ValidationError, WorkspaceError:
        return None
    located = {point.id: point.position_mm for point in report.points}
    stored = {landmark.id: landmark.position_mm for landmark in atlas.landmarks}
    stored[atlas.target.id] = atlas.target.position_mm
    return report if located == stored else None


# ---- building ----------------------------------------------------------------


def build(workspace: WorkspaceFiles, request: AtlasBuildRequest) -> AtlasDetail:
    """Pose every image of the set on the board, triangulate the clicks, write the atlas."""
    folder = workspace.view_set(request.view_set)
    intrinsics = find_intrinsics(workspace, request.camera_id)
    rig = measured_board(workspace, request.board)
    clicks = _clicks(workspace, folder, request)
    _check_image_size(workspace, folder, request.view_set, intrinsics)

    board = create_board(
        rig["squares_x"],
        rig["squares_y"],
        rig["square_mm"],
        rig["marker_mm"],
        rig["dictionary_id"],
        rig["marker_ids"],
    )
    detector = cv.aruco.CharucoDetector(board)
    rng = np.random.default_rng(request.seed)
    try:
        poses = pose_views(
            read_images(folder), detector, board, intrinsics, rng, samples=request.samples
        )
    except (OSError, ValueError) as error:
        # Paths in the message become relative: read_images names files in full.
        message = str(error).replace(f"{folder}{os.sep}", "")
        raise Conflict(f"view set {request.view_set!r}: {message}") from error

    try:
        atlas, report = build_atlas(
            poses,
            clicks,
            intrinsics,
            asset_id=request.asset_id,
            version=request.version,
            frame=f"board:{request.board}",
            target_id=request.target_id,
            target_extent_mm=request.target_extent_mm,
            click_sigma_px=request.click_sigma_px,
            target_centre_sigma_mm=request.target_centre_sigma_mm,
            seed=request.seed,
        )
    except ValueError as error:
        raise Conflict(str(error)) from error

    build_report = _build_report(request, atlas, report, poses)
    atlas_dir = workspace.folder_for_writing(workspace.atlas_dir)
    with _lock:
        # The atlas first: a report never describes an atlas that is not there.
        write_atomic(atlas_dir / f"{request.asset_id}.json", _json(atlas))
        write_atomic(atlas_dir / f"{request.asset_id}{REPORT_SUFFIX}", _json(build_report))
    return AtlasDetail(atlas=atlas, report=build_report)


def _clicks(workspace: WorkspaceFiles, folder: Path, request: AtlasBuildRequest) -> Clicks:
    path = workspace.clicks_file(folder)
    if path is None:
        raise Conflict(f"view set {request.view_set!r} has no clicks")
    try:
        clicks = load_clicks(workspace, path)
    except Invalid as error:
        raise Conflict(str(error)) from error
    if clicks.camera_id != request.camera_id:
        clicked_on = repr(clicks.camera_id) if clicks.camera_id else "no camera"
        raise Conflict(
            f"the clicks of view set {request.view_set!r} name {clicked_on}, "
            f"not {request.camera_id!r}"
        )
    return clicks


def _check_image_size(
    workspace: WorkspaceFiles, folder: Path, name: str, intrinsics: Intrinsics
) -> None:
    """Fail unless every image has the size the camera was calibrated at."""
    sizes = set()
    for path in workspace.images(folder):
        header = read_header(path)
        if header.width is None or header.height is None:
            raise Conflict(f"{path.name} in view set {name!r}: {header.error}")
        sizes.add((header.width, header.height))
    if not sizes:
        raise Conflict(f"view set {name!r} has no images")
    if len(sizes) > 1:
        listed = ", ".join(f"{width}x{height}" for width, height in sorted(sizes))
        raise Conflict(f"view set {name!r} has images of several sizes: {listed} px")
    (size,) = sizes
    if size != intrinsics["image_size"]:
        width, height = intrinsics["image_size"]
        rotated = " (rotated by 90 degrees)" if size == (height, width) else ""
        raise Conflict(
            f"the images of view set {name!r} are {size[0]}x{size[1]} px{rotated}, but "
            f"{intrinsics['camera_id']} was calibrated at {width}x{height} px"
        )


def _build_report(
    request: AtlasBuildRequest, atlas: Atlas, report: AtlasReport, poses: dict[str, ViewPose]
) -> AtlasBuildReport:
    """The numbers tools/build_atlas.py prints, as data."""
    located = report["points"]
    points = []
    for point_id in sorted(located):
        estimate = located[point_id]
        is_target = point_id == request.target_id
        points.append(
            AtlasPoint(
                id=point_id,
                position_mm=_vec3(estimate["position_mm"]),
                sigma_mm=atlas.target.sigma_mm if is_target else estimate["sigma_mm"],
                triangulation_sigma_mm=estimate["sigma_mm"],
                views=report["views_per_point"][point_id],
                worst_px=float(estimate["residuals_px"].max()),
                ray_angle_deg=estimate["ray_angle_deg"],
                is_target=is_target,
            )
        )
    gap = None
    if request.target_measured_mm is not None:
        offset = located[request.target_id]["position_mm"] - np.array(request.target_measured_mm)
        gap = float(np.linalg.norm(offset))
    return AtlasBuildReport(
        built_at=now(),
        request=request,
        posed_views=[
            PosedView(file=name, corners=pose["corners"], rms_px=pose["rms_px"])
            for name, pose in sorted(poses.items())
        ],
        unposed_views=report["unposed_views"],
        points=points,
        skipped=report["skipped"],
        target_gap_mm=gap,
    )


def _vec3(position: np.ndarray) -> Vec3:
    return (float(position[0]), float(position[1]), float(position[2]))


def _json(model: Atlas | AtlasBuildReport) -> bytes:
    """Indented like the CLI writes an atlas, so the files diff cleanly."""
    return (model.model_dump_json(indent=2) + "\n").encode("utf-8")
