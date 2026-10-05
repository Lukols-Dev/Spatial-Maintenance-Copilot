"""Calibrate a camera from a folder of ChArUco board photos."""

import numpy as np
from smc_core.calibration import Calibration

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
