"""Calibrate a camera from a video, or a folder of images, of the ChArUco board."""

import argparse
from pathlib import Path

import cv2 as cv
import numpy as np
from smc_core.calibration import (
    Calibration,
    calibrate,
    collect_correspondences,
    create_board,
    save_calibration,
)
from smc_core.images import read_images
from smc_core.rig import load_rig_board
from smc_core.video import read_video_frames

PARAMETER_NAMES = ["fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2", "k3"]
RIG_FILE = Path(__file__).resolve().parents[1] / "calib" / "rig.yaml"


def keep_views(per_view_errors: np.ndarray, max_error: float) -> list[int]:
    """Indices of the views whose RMS reprojection error is at most max_error px."""
    return [index for index, error in enumerate(per_view_errors) if error <= max_error]


def format_report(result: Calibration, used: list[str], image_size: tuple[int, int]) -> str:
    """Text summary of a calibration: the numbers to read before trusting it."""
    camera_matrix = result["camera_matrix"]
    values = [
        camera_matrix[0, 0],
        camera_matrix[1, 1],
        camera_matrix[0, 2],
        camera_matrix[1, 2],
        *result["dist_coeffs"],
    ]

    lines = [
        f"views used: {len(used)}",
        f"image size: {image_size[0]}x{image_size[1]} px",
        f"RMS reprojection error: {result['rms']:.3f} px",
        "",
        "parameters, value +/- standard deviation:",
    ]
    for name, value, std in zip(PARAMETER_NAMES, values, result["std_intrinsics"][:9], strict=True):
        lines.append(f"  {name}  {value:11.4f} +/- {std:.4f}")

    lines += ["", "error per view, worst first:"]
    for index in np.argsort(result["per_view_errors"])[::-1]:
        lines.append(f"  {result['per_view_errors'][index]:.3f} px  {used[index]}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="video of the board, or a folder of images")
    parser.add_argument("--out", type=Path, required=True, help="file to write, e.g. calib/x.yml")
    parser.add_argument("--camera-id", required=True, help="capture mode the result is valid for")
    parser.add_argument("--step", type=int, default=30, help="use every n-th video frame")
    parser.add_argument(
        "--rig", type=Path, default=RIG_FILE, help="measured boards, default calib/rig.yaml"
    )
    parser.add_argument(
        "--fix-k3", action="store_true", help="hold k3 at zero, e.g. when its std exceeds its value"
    )
    parser.add_argument(
        "--max-view-error", type=float, help="drop views above this error in px, then recalibrate"
    )
    args = parser.parse_args(argv)

    # The printed calibration board, sized by the caliper reading in the rig file.
    rig = load_rig_board(args.rig, "calibration_board")
    board = create_board(
        rig["squares_x"],
        rig["squares_y"],
        rig["square_mm"],
        rig["marker_mm"],
        rig["dictionary_id"],
        rig["marker_ids"],
    )
    detector = cv.aruco.CharucoDetector(board)

    if args.source.is_dir():
        frames = read_images(args.source)
    else:
        frames = read_video_frames(args.source, args.step)

    object_points, image_points, used, image_size = collect_correspondences(detector, board, frames)
    if image_size is None:
        raise SystemExit(f"no frame in {args.source} shows enough of the board")

    result = calibrate(object_points, image_points, image_size, fix_k3=args.fix_k3)

    if args.max_view_error is not None:
        keep = keep_views(result["per_view_errors"], args.max_view_error)
        if not keep:
            raise SystemExit(f"no view has an error at most {args.max_view_error} px")
        dropped = [used[index] for index in range(len(used)) if index not in keep]
        print(f"dropped {len(dropped)} views above {args.max_view_error} px: {', '.join(dropped)}")

        object_points = [object_points[index] for index in keep]
        image_points = [image_points[index] for index in keep]
        used = [used[index] for index in keep]
        result = calibrate(object_points, image_points, image_size, fix_k3=args.fix_k3)

    print(format_report(result, used, image_size))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    save_calibration(str(args.out), result, image_size, args.camera_id)
    print(f"\nsaved: {args.out}")


if __name__ == "__main__":
    main()
