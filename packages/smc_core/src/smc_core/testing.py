"""A synthetic scene with known truth, for tests.

A portrait phone camera without lens distortion looks at the rig board from
eight viewpoints, and points around a cabinet are clicked in every view with a
chosen pixel error. The tests of smc_core and of the services that wrap it
build their scenes from here, so they all check against the same truth.
Nothing in the pipeline imports this module.
"""

from collections.abc import Iterator

import cv2 as cv
import numpy as np

from smc_core.calibration import Calibration, Intrinsics, create_board
from smc_core.contracts import Clicks, Vec2, Vec3

CAMERA_ID = "phone-1x-portrait"
INTRINSICS: Intrinsics = {
    "camera_id": CAMERA_ID,
    "image_size": (1080, 1920),
    "camera_matrix": np.array([[1675.0, 0.0, 531.6], [0.0, 1677.4, 956.2], [0.0, 0.0, 1.0]]),
    "dist_coeffs": np.zeros(5),
    "rms": 0.3,
    "std_intrinsics": np.zeros(9),
}

# The rig board: 4x6 squares of 25 mm, markers 18 mm, ids 20 to 31.
SQUARE_MM = 25.0
BOARD_CENTRE = np.array([50.0, 75.0, 0.0])
PX_PER_SQUARE = 60
MARGIN_PX = 20

# Points in the board frame, spread over depth the way landmarks on and around a
# cabinet would be, and the target behind them.
POINTS_MM = {
    "corner_top_left": np.array([-120.0, -160.0, 150.0]),
    "corner_top_right": np.array([210.0, -150.0, 140.0]),
    "corner_bottom_left": np.array([-110.0, 280.0, 90.0]),
    "corner_bottom_right": np.array([200.0, 290.0, 100.0]),
    "handle_screw": np.array([40.0, 60.0, 130.0]),
    "box_on_top": np.array([100.0, -170.0, -60.0]),
    "drone": np.array([60.0, 90.0, 420.0]),
}
TARGET_ID = "drone"
EXTENT_MM: Vec3 = (300.0, 300.0, 100.0)

# Eight viewpoints at 0.6 to 0.8 m, turned left, right, up and down.
VIEWPOINTS = [
    ([0.35, 0.10, 0.0], 650.0),
    ([-0.35, 0.15, 0.05], 700.0),
    ([0.20, -0.40, 0.0], 600.0),
    ([-0.15, 0.45, -0.05], 750.0),
    ([0.45, 0.35, 0.1], 800.0),
    ([-0.40, -0.35, 0.0], 700.0),
    ([0.05, 0.50, 0.0], 650.0),
    ([-0.30, 0.0, -0.1], 600.0),
]


def rig_board() -> cv.aruco.CharucoBoard:
    return create_board(4, 6, SQUARE_MM, 18.0, cv.aruco.DICT_5X5_100, list(range(20, 32)))


def calibration() -> Calibration:
    """INTRINSICS as `calibrate` would return them, ready for `save_calibration`."""
    return {
        "rms": INTRINSICS["rms"],
        "camera_matrix": INTRINSICS["camera_matrix"],
        "dist_coeffs": INTRINSICS["dist_coeffs"],
        "std_intrinsics": np.zeros(18),
        "per_view_errors": np.array([0.3]),
    }


def camera_pose(rvec: list[float], distance_mm: float) -> tuple[np.ndarray, np.ndarray]:
    """A camera that looks at the board centre from distance_mm, turned by rvec."""
    rotation, _ = cv.Rodrigues(np.array(rvec))
    return rotation, -rotation @ BOARD_CENTRE + np.array([0.0, 0.0, distance_mm])


def render(board: cv.aruco.CharucoBoard, rotation: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    """The board on a white wall as this camera sees it, without lens distortion."""
    source = board.generateImage(
        (4 * PX_PER_SQUARE + 2 * MARGIN_PX, 6 * PX_PER_SQUARE + 2 * MARGIN_PX), marginSize=MARGIN_PX
    )
    scale = PX_PER_SQUARE / SQUARE_MM
    pixel_to_mm = np.array(
        [[1 / scale, 0, -MARGIN_PX / scale], [0, 1 / scale, -MARGIN_PX / scale], [0, 0, 1]]
    )
    homography = (
        INTRINSICS["camera_matrix"]
        @ np.column_stack([rotation[:, 0], rotation[:, 1], tvec])
        @ pixel_to_mm
    )
    return cv.warpPerspective(source, homography, (1080, 1920), borderValue=255)


def project(points_mm: np.ndarray, rotation: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    rvec, _ = cv.Rodrigues(rotation)
    projected, _ = cv.projectPoints(
        points_mm.reshape(-1, 3), rvec, tvec, INTRINSICS["camera_matrix"], INTRINSICS["dist_coeffs"]
    )
    return projected.reshape(-1, 2)


def rendered_views(board: cv.aruco.CharucoBoard) -> Iterator[tuple[str, np.ndarray]]:
    """(file name, frame) of every viewpoint, named the way clicks_for names them."""
    for index, (rvec, distance) in enumerate(VIEWPOINTS):
        yield f"view_{index}.png", render(board, *camera_pose(rvec, distance))


def clicks_for(sigma_px: float, names: list[str] | None = None) -> Clicks:
    """Every point clicked in every view, each click off by sigma_px.

    names keeps only those views. The file has no points list, like one
    written before the annotator kept it.
    """
    rng = np.random.default_rng(1)
    marks: dict[str, dict[str, Vec2]] = {}
    for index, (rvec, distance) in enumerate(VIEWPOINTS):
        rotation, tvec = camera_pose(rvec, distance)
        marked: dict[str, Vec2] = {}
        for point_id, point in POINTS_MM.items():
            pixel = project(point, rotation, tvec)[0] + rng.normal(0, sigma_px, 2)
            marked[point_id] = (float(pixel[0]), float(pixel[1]))
        marks[f"view_{index}.png"] = marked
    if names is not None:
        marks = {name: marks[name] for name in names}
    return Clicks(camera_id=CAMERA_ID, views=marks)
