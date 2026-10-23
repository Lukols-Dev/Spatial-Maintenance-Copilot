"""Hold a stored camera calibration against a new video of the calibration board.

A camera calibrated once is taken to stay calibrated; this checks it on the day
of a recording session. The video is calibrated afresh, as calibrate_camera.py
does it, and the two are held against each other twice:

- the stored model's reprojection error on the new views against the fresh
  fit's, which is made for those views and so always does a little better;
- the focal length and the principal point, which a planar board's poses can
  partly absorb, so that a few per cent of focal length hardly shows in the
  error alone.

The stored calibration still describes the camera while both hold.

    uv run tools/check_calibration.py data/cabinet-aruco/2026-10-23/calib/calib.MOV \\
        --intrinsics calib/intrinsics/iphone11-1x-1080p-portrait.yml
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2 as cv
import numpy as np
from calibrate_camera import PARAMETER_NAMES
from smc_core.calibration import (
    Calibration,
    Intrinsics,
    calibrate,
    collect_correspondences,
    create_board,
    load_calibration,
)
from smc_core.rig import load_rig_board
from smc_core.video import read_video_frames

RIG_FILE = Path(__file__).resolve().parents[1] / "calib" / "rig.yaml"
# The stored model still fits while its error on today's views stays within
# this much of the fresh fit's: a fifth more, or 0.15 px for a small error.
FITS_RATIO = 1.2
FITS_PX = 0.15
# ... and while the fresh focal length and principal point stay this close to the
# stored ones: some five standard deviations of a calibration from one video.
FOCAL_SHARE = 0.01
CENTRE_PX = 15.0


@dataclass(frozen=True)
class CalibrationCheck:
    views: int
    fresh: Calibration
    stored: Intrinsics
    stored_rms_px: float

    @property
    def misfits(self) -> list[str]:
        """Where the stored calibration and today's views part; none while it still fits."""
        fresh, stored = self.fresh["camera_matrix"], self.stored["camera_matrix"]
        found = []
        if self.stored_rms_px > max(FITS_RATIO * self.fresh["rms"], self.fresh["rms"] + FITS_PX):
            found.append(
                f"its reprojection error, {self.stored_rms_px:.2f} px, is well above the fresh "
                f"fit's {self.fresh['rms']:.2f} px"
            )
        for name, index in (("fx", 0), ("fy", 1)):
            shift = fresh[index, index] / stored[index, index] - 1
            if abs(shift) > FOCAL_SHARE:
                found.append(f"{name} has moved by {shift:+.1%}")
        for name, row in (("cx", 0), ("cy", 1)):
            shift = fresh[row, 2] - stored[row, 2]
            if abs(shift) > CENTRE_PX:
                found.append(f"{name} has moved by {shift:+.0f} px")
        return found

    @property
    def fits(self) -> bool:
        return not self.misfits


def stored_rms(
    object_points: list[np.ndarray], image_points: list[np.ndarray], intrinsics: Intrinsics
) -> float:
    """The RMS reprojection error of a stored model over views it was not fitted to, each view posed by it."""
    camera_matrix, dist_coeffs = intrinsics["camera_matrix"], intrinsics["dist_coeffs"]
    squared: list[np.ndarray] = []
    for board_points, image_pixels in zip(object_points, image_points, strict=True):
        obj = board_points.reshape(-1, 3).astype(np.float64)
        img = image_pixels.reshape(-1, 2).astype(np.float64)
        found, rvec, tvec = cv.solvePnP(
            obj, img, camera_matrix, dist_coeffs, flags=cv.SOLVEPNP_IPPE
        )
        if not found:
            continue
        rvec, tvec = cv.solvePnPRefineLM(obj, img, camera_matrix, dist_coeffs, rvec, tvec)
        projected, _ = cv.projectPoints(obj, rvec, tvec, camera_matrix, dist_coeffs)
        squared.append(np.sum((projected.reshape(-1, 2) - img) ** 2, axis=1))
    if not squared:
        raise ValueError("no view could be posed with the stored calibration")
    return float(np.sqrt(np.mean(np.concatenate(squared))))


def check_calibration(
    video: Path, intrinsics: Intrinsics, board: cv.aruco.CharucoBoard, step: int
) -> CalibrationCheck:
    """A fresh calibration of the video's views, and the stored model's error on them."""
    detector = cv.aruco.CharucoDetector(board)
    object_points, image_points, used, size = collect_correspondences(
        detector, board, read_video_frames(video, step)
    )
    if size is None:
        raise ValueError(f"no frame of {video.name} shows enough of the calibration board")
    if size != intrinsics["image_size"]:
        width, height = intrinsics["image_size"]
        raise ValueError(
            f"{video.name} is {size[0]}x{size[1]} px, {intrinsics['camera_id']} was "
            f"calibrated at {width}x{height} px"
        )
    return CalibrationCheck(
        views=len(used),
        fresh=calibrate(object_points, image_points, size),
        stored=intrinsics,
        stored_rms_px=stored_rms(object_points, image_points, intrinsics),
    )


def format_check(check: CalibrationCheck) -> str:
    """The stored and the fresh parameters side by side, then the two errors and what they say."""
    stored_matrix, fresh_matrix = check.stored["camera_matrix"], check.fresh["camera_matrix"]
    stored = [
        stored_matrix[0, 0],
        stored_matrix[1, 1],
        stored_matrix[0, 2],
        stored_matrix[1, 2],
        *check.stored["dist_coeffs"],
    ]
    fresh = [
        fresh_matrix[0, 0],
        fresh_matrix[1, 1],
        fresh_matrix[0, 2],
        fresh_matrix[1, 2],
        *check.fresh["dist_coeffs"],
    ]
    lines = [
        f"  {check.views} views of the calibration board",
        f"  {'':4s} {'stored':>11s} {'fresh':>11s} {'+/- std':>9s} {'in std':>7s}",
    ]
    for name, then, now, std in zip(
        PARAMETER_NAMES, stored, fresh, check.fresh["std_intrinsics"][:9], strict=True
    ):
        shift = f"{(now - then) / std:+7.1f}" if std > 0 else f"{'-':>7s}"
        lines.append(f"  {name:4s} {then:11.4f} {now:11.4f} {std:9.4f} {shift}")
    lines.append(
        f"  RMS reprojection on these views: fresh {check.fresh['rms']:.3f} px, "
        f"stored {check.stored_rms_px:.3f} px"
    )
    if check.fits:
        lines.append("  the stored calibration still describes the camera")
    else:
        lines.append(
            "  the stored calibration no longer describes the camera: a new one needs a new camera id"
        )
        lines += [f"    {misfit}" for misfit in check.misfits]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("video", type=Path, help="a video of the calibration board")
    parser.add_argument("--intrinsics", type=Path, required=True, help="the stored calibration")
    parser.add_argument("--step", type=int, default=30, help="use every n-th video frame")
    parser.add_argument("--rig", type=Path, default=RIG_FILE, help="measured boards")
    args = parser.parse_args(argv)

    rig = load_rig_board(args.rig, "calibration_board")
    board = create_board(
        rig["squares_x"],
        rig["squares_y"],
        rig["square_mm"],
        rig["marker_mm"],
        rig["dictionary_id"],
        rig["marker_ids"],
    )
    try:
        check = check_calibration(
            args.video, load_calibration(str(args.intrinsics)), board, args.step
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(format_check(check))


if __name__ == "__main__":
    main()
