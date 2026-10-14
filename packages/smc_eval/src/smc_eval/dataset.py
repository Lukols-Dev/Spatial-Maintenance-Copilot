"""A frozen evaluation dataset: what the evaluation reads, checked against its manifest.

One folder of eval/datasets/, kept in git:

    manifest.json                 what was frozen, from which media, each file's SHA-256
    atlas.json                    the Component Atlas as evaluated
    atlas.report.json             its build report, which holds the click sigma
    sets/<set>/clicks.json        the clicks of a view set
    sets/<set>/board_poses.json   where the rig board puts the camera, in each frame it is found

The camera's intrinsics stay in calib/intrinsics/, already in git, and the
manifest holds their SHA-256. The videos and the exported frames are private
and stay out of git: the manifest names each with its SHA-256, so a result
traces back to the exact media. Loading checks every frozen file and the camera
file against the manifest, so a changed input stops the evaluation instead of
changing its numbers.

A test set was recorded apart from the views the atlas was built from, and is
what the evaluation scores. A build set is those views: whatever is measured
on it is in-sample, and the report says so.
"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2 as cv
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from smc_core.board_pose import board_view_pose
from smc_core.calibration import Intrinsics, create_board, load_calibration
from smc_core.contracts import Atlas, Clicks, Contract, Pose, load_atlas, load_clicks
from smc_core.images import read_images
from smc_core.rig import load_rig_board

MANIFEST = "manifest.json"
ATLAS = "atlas.json"
ATLAS_REPORT = "atlas.report.json"
CLICKS = "clicks.json"
BOARD_POSES = "board_poses.json"
VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v"}

Role = Literal["test", "build"]


class DatasetError(Exception):
    """The inputs cannot be frozen, or a frozen folder does not match its manifest."""


class MediaFile(Contract):
    """A file of the workspace the dataset was frozen from or reads."""

    path: str = Field(description="from the workspace root")
    sha256: str
    bytes: int
    size_px: tuple[int, int] | None = Field(default=None, description="width, height of a frame")


class BoardPose(Contract):
    """Where the rig board puts the camera: the reference the landmark pose is held against."""

    pose: Pose
    corners: int
    rms_px: float


class BoardPoses(Contract):
    board: str
    poses: dict[str, BoardPose] = Field(
        description="by frame; frames without the board are left out"
    )


class FrozenSet(Contract):
    name: str
    role: Role
    frames: list[MediaFile]


class Manifest(Contract):
    name: str
    frozen_at: str
    git_commit: str | None
    asset_id: str
    atlas_version: str
    camera_id: str
    board: str = Field(description="the rig board that defines the asset frame")
    camera: MediaFile = Field(description="the intrinsics, read from the workspace")
    rig: MediaFile
    videos: list[MediaFile]
    sets: list[FrozenSet]
    files: dict[str, str] = Field(
        description="SHA-256 of every file of the folder but the manifest"
    )


class _BuildRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    click_sigma_px: float


class _BuildReport(BaseModel):
    """The part of an atlas build report the evaluation reads."""

    model_config = ConfigDict(extra="ignore")

    request: _BuildRequest


@dataclass(frozen=True, eq=False)
class ViewSet:
    name: str
    role: Role
    clicks: Clicks
    board_poses: dict[str, BoardPose]


@dataclass(frozen=True, eq=False)
class Dataset:
    """A frozen dataset as the evaluation reads it; sigma_px is the click sigma of the atlas build."""

    name: str
    manifest_sha256: str
    atlas: Atlas
    intrinsics: Intrinsics
    sigma_px: float
    sets: dict[str, ViewSet]

    def with_role(self, role: Role) -> list[ViewSet]:
        return [view_set for view_set in self.sets.values() if view_set.role == role]


def sha256_of(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def media_file(path: Path, root: Path, size_px: tuple[int, int] | None = None) -> MediaFile:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise DatasetError(f"{path} is outside the workspace {root}") from error
    return MediaFile(
        path=relative.as_posix(), sha256=sha256_of(path), bytes=path.stat().st_size, size_px=size_px
    )


def videos_in(folder: Path) -> list[Path]:
    """Every video under folder, at any depth, in path order."""
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    )


# ---- freezing ------------------------------------------------------------------------


def freeze(
    out: Path,
    *,
    name: str,
    root: Path,
    atlas_file: Path,
    camera_file: Path,
    rig_file: Path,
    videos: Iterable[Path],
    sets: Iterable[tuple[Path, Role]],
    frozen_at: str,
    git_commit: str | None,
) -> Manifest:
    """Copy what the evaluation reads into out, pose every frame by the board, write the manifest.

    The board is the one that defines the atlas frame, so its poses are in the
    frame the landmark poses are. Each view set is a folder of frames with its
    clicks.json, as export_views.py and the annotator leave it; every frame
    must have the size the camera was calibrated at, since clicks in another
    size are pixels of another camera model. A frozen dataset is never
    changed: out must not exist yet.
    """
    if out.exists():
        raise DatasetError(
            f"{out} exists: a frozen dataset is not changed, freeze under a new name"
        )
    report_file = atlas_file.with_name(f"{atlas_file.stem}.report.json")
    if not report_file.is_file():
        raise DatasetError(f"{report_file} is missing: the click sigma comes from the build report")
    atlas = load_atlas(atlas_file)
    board = atlas.frame.removeprefix("board:")
    if board == atlas.frame:
        raise DatasetError(f"the atlas frame {atlas.frame!r} is not a rig board's")
    intrinsics = load_calibration(str(camera_file))
    try:
        rig = load_rig_board(rig_file, board)
    except ValueError as error:
        raise DatasetError(str(error)) from error
    charuco = create_board(
        rig["squares_x"],
        rig["squares_y"],
        rig["square_mm"],
        rig["marker_mm"],
        rig["dictionary_id"],
        rig["marker_ids"],
    )
    detector = cv.aruco.CharucoDetector(charuco)

    frozen: dict[str, bytes] = {
        ATLAS: atlas_file.read_bytes(),
        ATLAS_REPORT: report_file.read_bytes(),
    }
    frozen_sets: list[FrozenSet] = []
    for folder, role in sets:
        clicks_file = folder / CLICKS
        if not clicks_file.is_file():
            raise DatasetError(f"{folder} has no {CLICKS}")
        clicks = load_clicks(clicks_file)
        if clicks.camera_id != intrinsics["camera_id"]:
            raise DatasetError(
                f"the clicks of {folder.name} are of {clicks.camera_id}, "
                f"the camera file of {intrinsics['camera_id']}"
            )
        frames: list[MediaFile] = []
        poses: dict[str, BoardPose] = {}
        for frame_name, frame in read_images(folder):
            height, width = frame.shape[:2]
            if (width, height) != intrinsics["image_size"]:
                raise DatasetError(
                    f"{folder.name}/{frame_name} is {width}x{height} px, but the camera was "
                    f"calibrated at {intrinsics['image_size'][0]}x{intrinsics['image_size'][1]} px"
                )
            frames.append(media_file(folder / frame_name, root, (width, height)))
            # No samples: the reference is the pose itself, not its spread.
            found = board_view_pose(
                detector, charuco, frame, intrinsics, np.random.default_rng(0), samples=0
            )
            if found is not None:
                rvec, _ = cv.Rodrigues(found["rotation"])
                tvec = found["tvec"]
                poses[frame_name] = BoardPose(
                    pose=Pose(
                        rvec=(float(rvec[0, 0]), float(rvec[1, 0]), float(rvec[2, 0])),
                        tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
                    ),
                    corners=found["corners"],
                    rms_px=found["rms_px"],
                )
        unknown = sorted(set(clicks.views) - {frame.path.rsplit("/", 1)[-1] for frame in frames})
        if unknown:
            raise DatasetError(f"{folder.name}: clicks of frames that are not there: {unknown}")
        frozen[f"sets/{folder.name}/{CLICKS}"] = clicks_file.read_bytes()
        frozen[f"sets/{folder.name}/{BOARD_POSES}"] = (
            BoardPoses(board=board, poses=poses).model_dump_json(indent=2) + "\n"
        ).encode()
        frozen_sets.append(FrozenSet(name=folder.name, role=role, frames=frames))
    if not any(view_set.role == "test" for view_set in frozen_sets):
        raise DatasetError("no test set: the evaluation scores views the atlas was not built from")

    for relative, content in frozen.items():
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = Manifest(
        name=name,
        frozen_at=frozen_at,
        git_commit=git_commit,
        asset_id=atlas.asset_id,
        atlas_version=atlas.version,
        camera_id=intrinsics["camera_id"],
        board=board,
        camera=media_file(camera_file, root),
        rig=media_file(rig_file, root),
        videos=[media_file(video, root) for video in videos],
        sets=frozen_sets,
        files={
            relative: hashlib.sha256(content).hexdigest() for relative, content in frozen.items()
        },
    )
    (out / MANIFEST).write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


# ---- reading -------------------------------------------------------------------------


def read_manifest(folder: Path) -> Manifest:
    path = folder / MANIFEST
    if not path.is_file():
        raise DatasetError(f"{folder} has no {MANIFEST}: not a frozen dataset")
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_dataset(folder: Path, root: Path) -> Dataset:
    """The frozen dataset in folder, every file checked; the camera file is read from root."""
    manifest = read_manifest(folder)
    problems = [
        f"{relative} {problem}"
        for relative, expected in manifest.files.items()
        if (problem := _differs(folder / relative, expected))
    ]
    camera_path = root / manifest.camera.path
    if problem := _differs(camera_path, manifest.camera.sha256):
        problems.append(f"{manifest.camera.path} {problem}")
    if problems:
        raise DatasetError(f"{folder} does not match its manifest: {'; '.join(problems)}")

    report = _BuildReport.model_validate_json((folder / ATLAS_REPORT).read_text(encoding="utf-8"))
    sets: dict[str, ViewSet] = {}
    for frozen in manifest.sets:
        base = folder / "sets" / frozen.name
        poses = BoardPoses.model_validate_json((base / BOARD_POSES).read_text(encoding="utf-8"))
        sets[frozen.name] = ViewSet(
            name=frozen.name,
            role=frozen.role,
            clicks=load_clicks(base / CLICKS),
            board_poses=poses.poses,
        )
    return Dataset(
        name=manifest.name,
        manifest_sha256=sha256_of(folder / MANIFEST),
        atlas=load_atlas(folder / ATLAS),
        intrinsics=load_calibration(str(camera_path)),
        sigma_px=report.request.click_sigma_px,
        sets=sets,
    )


def check_media(manifest: Manifest, root: Path) -> list[str]:
    """The media the dataset was frozen from that is missing or changed in root."""
    media = [*manifest.videos, *(frame for view_set in manifest.sets for frame in view_set.frames)]
    return [
        f"{file.path} {problem}"
        for file in media
        if (problem := _differs(root / file.path, file.sha256))
    ]


def _differs(path: Path, sha256: str) -> str | None:
    if not path.is_file():
        return "is missing"
    if sha256_of(path) != sha256:
        return "has changed since the freeze"
    return None
