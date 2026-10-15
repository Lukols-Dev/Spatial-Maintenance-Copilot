from typing import TypedDict

import cv2 as cv
import numpy as np

from smc_core.board_pose import ViewPose
from smc_core.calibration import Intrinsics
from smc_core.contracts import Atlas, Clicks, Landmark, Pose, Target, Vec3
from smc_core.guidance import choose_guide_view
from smc_core.markers import tag_point_ids
from smc_core.triangulate import PointEstimate, locate_point


class AtlasReport(TypedDict):
    """What went into an atlas, for reading before trusting it."""

    points: dict[str, PointEstimate]  # every point that was located, target included
    views_per_point: dict[str, int]  # posed views each located point was seen in
    skipped: dict[str, str]  # point id -> why it is not in the atlas
    unposed_views: list[str]  # views with clicks in which the board was not found


def build_atlas(
    poses: dict[str, ViewPose],
    clicks: Clicks,
    intrinsics: Intrinsics,
    *,
    asset_id: str,
    version: str,
    frame: str,
    target_id: str,
    target_extent_mm: Vec3,
    click_sigma_px: float,
    target_centre_sigma_mm: float,
    seed: int = 0,
    target_tag_depth_mm: float | None = None,
) -> tuple[Atlas, AtlasReport]:
    """Triangulate every clicked point in the board frame and assemble the atlas.

    poses: view name -> pose, for the views in which the board was found. Views
    without a pose cannot be used and are listed in the report.

    Every point except target_id becomes a landmark. A point needs clicks in at
    least two posed views. The target is a box, not a point, so the position of
    its centre is uncertain by more than the clicks say: target_centre_sigma_mm
    is added in quadrature.

    With target_tag_depth_mm, the target is a box with a tag on one face, as
    markers.clicks_of marks it: target_id is the centre of the tag, and the
    four corners of the tag, <target_id>_0 to _3, orient the box. The box then
    stands behind the tag: target_extent_mm runs along the tag's width, its
    height and into the box, and the depth is target_tag_depth_mm. Those
    corners are never landmarks; without the option they are left out too.

    The atlas's guide view is the posed view that saw the most landmarks, the
    target nearest the middle among equals (guidance.choose_guide_view).

    Raises ValueError when the target cannot be located, since an atlas
    without a target has no use, or when its tag cannot orient its box.
    """
    if clicks.camera_id != intrinsics["camera_id"]:
        raise ValueError(
            f"clicks were made on {clicks.camera_id} frames, "
            f"but the intrinsics are for {intrinsics['camera_id']}"
        )

    unposed = sorted(name for name in clicks.views if name not in poses)
    observations: dict[str, list[tuple[ViewPose, tuple[float, float]]]] = {}
    for name in sorted(clicks.views):
        if name not in poses:
            continue
        for point_id, pixel in clicks.views[name].items():
            observations.setdefault(point_id, []).append((poses[name], pixel))

    rng = np.random.default_rng(seed)
    points: dict[str, PointEstimate] = {}
    skipped: dict[str, str] = {}
    for point_id in sorted(observations):
        seen = observations[point_id]
        if len(seen) < 2:
            skipped[point_id] = f"seen in {len(seen)} posed view, needs 2"
            continue
        estimate = locate_point(seen, intrinsics, click_sigma_px, rng)
        if estimate is None:
            skipped[point_id] = "could not be triangulated: behind a camera or too unstable"
            continue
        points[point_id] = estimate

    if target_id not in points:
        reason = skipped.get(target_id, "never clicked")
        raise ValueError(f"target {target_id!r} is not located: {reason}")

    def vec(position: np.ndarray) -> Vec3:
        return (float(position[0]), float(position[1]), float(position[2]))

    def landmark(point_id: str, estimate: PointEstimate) -> Landmark:
        seen_from, within_deg = _seen_from(
            estimate["position_mm"], [pose for pose, _ in observations[point_id]]
        )
        return Landmark(
            id=point_id,
            position_mm=vec(estimate["position_mm"]),
            sigma_mm=estimate["sigma_mm"],
            seen_from=vec(seen_from),
            seen_within_deg=within_deg,
        )

    tag = tag_point_ids(target_id)
    rvec: Vec3 = (0.0, 0.0, 0.0)
    offset: Vec3 = (0.0, 0.0, 0.0)
    if target_tag_depth_mm is not None:
        missing = [point_id for point_id in tag if point_id not in points]
        if missing:
            raise ValueError(f"the target's tag cannot orient its box: {missing} not located")
        tag_poses = [pose for pose, _ in observations[target_id]]
        rvec = _tag_rvec(np.array([points[point_id]["position_mm"] for point_id in tag]), tag_poses)
        offset = (0.0, 0.0, -target_tag_depth_mm / 2)

    centre = points[target_id]
    atlas = Atlas(
        asset_id=asset_id,
        version=version,
        frame=frame,
        landmarks=[
            landmark(point_id, estimate)
            for point_id, estimate in points.items()
            if point_id != target_id and point_id not in tag
        ],
        target=Target(
            id=target_id,
            position_mm=vec(centre["position_mm"]),
            sigma_mm=float(np.hypot(centre["sigma_mm"], target_centre_sigma_mm)),
            extent_mm=target_extent_mm,
            rvec=rvec,
            box_offset_mm=offset,
        ),
    )
    guide = choose_guide_view(
        {name: board_pose(pose) for name, pose in poses.items()}, clicks, atlas, intrinsics
    )
    atlas = atlas.model_copy(update={"guide_view": guide})
    report: AtlasReport = {
        "points": points,
        "views_per_point": {pid: len(observations[pid]) for pid in points},
        "skipped": skipped,
        "unposed_views": unposed,
    }
    return atlas, report


def _seen_from(position: np.ndarray, poses: list[ViewPose]) -> tuple[np.ndarray, float]:
    """The mean direction from a point to these cameras, and the widest angle off it.

    A camera's centre in the board frame is -R^T t. The mean of the unit
    directions, normalised, is where the point was seen from; the widest angle
    between it and one of them bounds the cone those cameras stood in.
    """
    centres = np.array([-pose["rotation"].T @ pose["tvec"] for pose in poses])
    directions = centres - position
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    mean = directions.sum(axis=0)
    mean /= np.linalg.norm(mean)
    widest = float(np.degrees(np.arccos(np.clip(directions @ mean, -1.0, 1.0))).max())
    return mean, widest


def _tag_rvec(corners: np.ndarray, poses: list[ViewPose]) -> Vec3:
    """The axes of a tag from its corners in the board frame: x along its width, y up it, z out of it.

    The corners come in OpenCV's order, top-left, top-right, bottom-right,
    bottom-left, so x runs from the left edge to the right and y from the
    bottom up; z, their cross product, then points out of the tag, towards
    the cameras that saw it. A tag whose z points away from them was not read
    in that order, and orients nothing.
    """
    top_left, top_right, bottom_right, bottom_left = corners
    x = (top_right - top_left) + (bottom_right - bottom_left)
    x /= np.linalg.norm(x)
    up = (top_left - bottom_left) + (top_right - bottom_right)
    y = up - (up @ x) * x
    y /= np.linalg.norm(y)
    z = np.cross(x, y)
    centre = corners.mean(axis=0)
    towards = np.mean([-pose["rotation"].T @ pose["tvec"] - centre for pose in poses], axis=0)
    if z @ towards <= 0:
        raise ValueError("the target's tag faces away from the cameras that saw it")
    rvec, _ = cv.Rodrigues(np.column_stack([x, y, z]))
    return (float(rvec[0, 0]), float(rvec[1, 0]), float(rvec[2, 0]))


def board_pose(pose: ViewPose) -> Pose:
    """A pose the rig board gave, as the atlas stores poses."""
    rvec, _ = cv.Rodrigues(pose["rotation"])
    tvec = pose["tvec"]
    return Pose(
        rvec=(float(rvec[0, 0]), float(rvec[1, 0]), float(rvec[2, 0])),
        tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
    )
