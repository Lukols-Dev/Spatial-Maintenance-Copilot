from pathlib import Path
from typing import TypedDict

import cv2 as cv
import yaml


class RigBoard(TypedDict):
    """One printed board from calib/rig.yaml, sized by its caliper measurement.

    Lengths are in millimetres. Every key but measurement_uncertainty_mm is an
    argument of `create_board`.
    """

    squares_x: int
    squares_y: int
    square_mm: float
    marker_mm: float
    dictionary_id: int
    marker_ids: list[int]
    measurement_uncertainty_mm: float | None


def load_rig_board(path: Path, key: str) -> RigBoard:
    """Read one board from calib/rig.yaml.

    The square side must be measured: the nominal value is what was sent to the
    printer, not what came out of it. An unmeasured marker side is scaled from
    the measured square, because the printer scales both by the same factor.
    """
    with path.open(encoding="utf-8") as file:
        rig = yaml.safe_load(file)

    if key not in rig["boards"]:
        raise ValueError(f"{path}: no board named {key!r}")
    board = rig["boards"][key]

    if board["square_measured_mm"] is None:
        raise ValueError(
            f"{path}: {key} has no square_measured_mm; measure the mounted board first"
        )
    square_mm = float(board["square_measured_mm"])

    if board["marker_measured_mm"] is None:
        marker_mm = square_mm * board["marker_nominal_mm"] / board["square_nominal_mm"]
    else:
        marker_mm = float(board["marker_measured_mm"])

    first_id, last_id = board["ids"]  # inclusive range
    uncertainty = board["measurement_uncertainty_mm"]

    return {
        "squares_x": int(board["squares_x"]),
        "squares_y": int(board["squares_y"]),
        "square_mm": square_mm,
        "marker_mm": marker_mm,
        "dictionary_id": getattr(cv.aruco, rig["dictionary"]),
        "marker_ids": list(range(first_id, last_id + 1)),
        "measurement_uncertainty_mm": None if uncertainty is None else float(uncertainty),
    }
