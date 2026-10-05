"""Calibrate a camera from a folder of ChArUco board photos."""

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

PARAMETER_NAMES = ["fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2", "k3"]


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
    parser.add_argument("images", type=Path, help="folder with photos of the calibration board")
    parser.add_argument("--out", type=Path, required=True, help="file to write, e.g. calib/x.yml")
    parser.add_argument("--camera-id", required=True, help="capture mode the result is valid for")
    args = parser.parse_args(argv)

    # The printed calibration board, as recorded in calib/rig.yaml.
    board = create_board(5, 7, 30.0, 21.6, cv.aruco.DICT_5X5_100, list(range(17)))
    detector = cv.aruco.CharucoDetector(board)

    object_points, image_points, used, image_size = collect_correspondences(
        detector, board, read_images(args.images)
    )
    if image_size is None:
        raise SystemExit(f"no photo in {args.images} shows enough of the board")

    result = calibrate(object_points, image_points, image_size)
    print(format_report(result, used, image_size))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    save_calibration(str(args.out), result, image_size, args.camera_id)
    print(f"\nsaved: {args.out}")


if __name__ == "__main__":
    main()
