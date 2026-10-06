"""Cameras: the calibration files in calib/intrinsics/."""

from pathlib import Path

from smc_core.calibration import Intrinsics, load_calibration_record

from smc_perception.errors import Conflict, NotFound
from smc_perception.models import Camera
from smc_perception.workspace import WorkspaceFiles

STD_NAMES = ["fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2", "k3"]


def list_cameras(workspace: WorkspaceFiles) -> list[Camera]:
    return [read_camera(workspace, path) for path in workspace.calibration_files()]


def read_camera(workspace: WorkspaceFiles, path: Path) -> Camera:
    """The calibration in one file; a file that cannot be read comes back with its error."""
    try:
        record = load_calibration_record(str(path))
        intrinsics = record["intrinsics"]
        matrix = intrinsics["camera_matrix"]
        return Camera(
            file=path.name,
            camera_id=intrinsics["camera_id"],
            image_width=intrinsics["image_size"][0],
            image_height=intrinsics["image_size"][1],
            frames=record["frames"],
            rms_px=intrinsics["rms"],
            fx=matrix[0, 0],
            fy=matrix[1, 1],
            cx=matrix[0, 2],
            cy=matrix[1, 2],
            dist_coeffs=intrinsics["dist_coeffs"].tolist(),
            std=dict(zip(STD_NAMES, intrinsics["std_intrinsics"].tolist(), strict=False)),
            calibrated_at=record["calibrated_at"],
            opencv_version=record["opencv_version"],
            error=None,
        )
    except Exception as error:
        # Whatever is wrong with one file, GET /workspace still answers.
        return broken_camera(path.name, _message(workspace, path, error))


def broken_camera(file: str, error: str) -> Camera:
    return Camera(
        file=file,
        camera_id=None,
        image_width=None,
        image_height=None,
        frames=None,
        rms_px=None,
        fx=None,
        fy=None,
        cx=None,
        cy=None,
        dist_coeffs=[],
        std={},
        calibrated_at=None,
        opencv_version=None,
        error=error,
    )


def _message(workspace: WorkspaceFiles, path: Path, error: Exception) -> str:
    """The reader's own words for an OSError or ValueError, with the path made relative."""
    if isinstance(error, OSError | ValueError):
        return str(error).replace(str(path), workspace.relative(path))
    return f"{workspace.relative(path)} is not a calibration written by save_calibration"


def find_intrinsics(workspace: WorkspaceFiles, camera_id: str) -> Intrinsics:
    """The intrinsics of camera_id, from the one file that calibrates it."""
    found: dict[str, Intrinsics] = {}
    for path in workspace.calibration_files():
        try:
            intrinsics = load_calibration_record(str(path))["intrinsics"]
        except OSError, ValueError:
            continue  # listed with its error by GET /workspace
        if intrinsics["camera_id"] == camera_id:
            found[path.name] = intrinsics
    if not found:
        raise NotFound(f"no calibration of camera {camera_id!r} in calib/intrinsics")
    if len(found) > 1:
        raise Conflict(f"camera {camera_id!r} is calibrated in several files: {', '.join(found)}")
    return next(iter(found.values()))
