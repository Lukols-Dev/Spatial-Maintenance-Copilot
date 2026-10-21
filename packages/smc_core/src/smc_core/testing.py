"""A synthetic scene with known truth, for tests.

A portrait phone camera without lens distortion looks at the rig board from
eight viewpoints, and points around a cabinet are clicked in every view with a
chosen pixel error. The tests of smc_core and of the services that wrap it
build their scenes from here, so they all check against the same truth.
Nothing in the pipeline imports this module.
"""

from collections.abc import Iterator
from functools import cache

import cv2 as cv
import numpy as np

from smc_core.calibration import Calibration, Intrinsics, create_board
from smc_core.contracts import Atlas, Clicks, Landmark, Panel, Target, Vec2, Vec3
from smc_core.markers import MarkerSet

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


# Printed markers stuck around the board, 40 mm, facing the cameras: corners in
# OpenCV's order (top-left, top-right, bottom-right, bottom-left) as a camera of
# VIEWPOINTS sees them upright. 50 to 55 are landmarks; 70 is the target's tag,
# behind the board's plane, on the face of a box MARKER_BOX_DEPTH_MM deep.
MARKER_SIDE_MM = 40.0
MARKER_BOX_DEPTH_MM = 60.0
TAG_ID = 70


def _square(left: float, top: float, z: float) -> np.ndarray:
    side = MARKER_SIDE_MM
    return np.array(
        [[left, top, z], [left + side, top, z], [left + side, top + side, z], [left, top + side, z]]
    )


MARKERS_MM: dict[int, np.ndarray] = {
    50: _square(-130.0, -60.0, -30.0),
    51: _square(190.0, -60.0, -30.0),
    52: _square(-130.0, 170.0, -30.0),
    53: _square(190.0, 170.0, -30.0),
    54: _square(30.0, -110.0, -80.0),
    55: _square(30.0, 220.0, 20.0),
    TAG_ID: _square(140.0, 60.0, 200.0),
}


def render_markers(
    frame: np.ndarray, placed: dict[int, np.ndarray], rotation: np.ndarray, tvec: np.ndarray
) -> np.ndarray:
    """The frame with each marker of DICT_5X5_100 drawn where its corners land, over what was there."""
    dictionary = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_5X5_100)
    size = (frame.shape[1], frame.shape[0])
    out = frame.copy()
    px = 210  # a multiple of the 7 modules of a 5x5 marker with its border
    # The marker's corners are the outer edges of its image's corner pixels.
    source = np.array(
        [[-0.5, -0.5], [px - 0.5, -0.5], [px - 0.5, px - 0.5], [-0.5, px - 0.5]], np.float32
    )
    for marker_id, corners in placed.items():
        image = cv.aruco.generateImageMarker(dictionary, marker_id, px, borderBits=1)
        homography = cv.getPerspectiveTransform(
            source, project(corners, rotation, tvec).astype(np.float32)
        )
        warped = cv.warpPerspective(image, homography, size, flags=cv.INTER_LINEAR, borderValue=255)
        inside = cv.warpPerspective(np.full_like(image, 255), homography, size) > 127
        out[inside] = warped[inside]
    return out


def rendered_marker_views(
    board: cv.aruco.CharucoBoard, placed: dict[int, np.ndarray]
) -> Iterator[tuple[str, np.ndarray]]:
    """(file name, frame) of every viewpoint: the board with those markers in front of it."""
    for index, (rvec, distance) in enumerate(VIEWPOINTS):
        rotation, tvec = camera_pose(rvec, distance)
        yield (
            f"view_{index}.png",
            render_markers(render(board, rotation, tvec), placed, rotation, tvec),
        )


# A door in front of the target's box, between it and the cameras; marker 50 is stuck on it.
DOOR_MM = [(100.0, 20.0, 150.0), (250.0, 20.0, 150.0), (250.0, 170.0, 150.0), (100.0, 170.0, 150.0)]
MARKER_SET = MarkerSet(cv.aruco.DICT_5X5_100, tuple(range(50, 61)), TAG_ID, MARKER_SIDE_MM)


@cache
def marker_atlas() -> Atlas:
    """The atlas of the marked scene, as the builder makes it from the rendered frames.

    Every marker corner is a landmark, the target is the tag's box, the door is
    its panel, and marker 50 moves with the door. Built once: it is the same
    every time.
    """
    from smc_core.atlas_build import build_atlas
    from smc_core.board_pose import pose_views
    from smc_core.markers import clicks_of, detect, marker_detector

    frames = list(rendered_marker_views(rig_board(), MARKERS_MM))
    detector = marker_detector(MARKER_SET)
    clicks = Clicks(
        camera_id=CAMERA_ID,
        views={
            name: clicks_of(detect(detector, MARKER_SET, frame), TARGET_ID)
            for name, frame in frames
        },
    )
    board = rig_board()
    poses = pose_views(
        frames,
        cv.aruco.CharucoDetector(board),
        board,
        INTRINSICS,
        np.random.default_rng(0),
        samples=20,
    )
    atlas, _ = build_atlas(
        poses,
        clicks,
        INTRINSICS,
        asset_id="home-cabinet",
        version="1",
        frame="board:rig_board_a",
        target_id=TARGET_ID,
        target_extent_mm=(30.0, 30.0, MARKER_BOX_DEPTH_MM),
        click_sigma_px=0.5,
        target_centre_sigma_mm=1.0,
        target_tag_depth_mm=MARKER_BOX_DEPTH_MM,
    )
    landmarks = [
        landmark.model_copy(
            update={"moves_with": "door" if landmark.id.startswith("m50_") else None}
        )
        for landmark in atlas.landmarks
    ]
    return Atlas.model_validate(
        atlas.model_dump()
        | {
            "landmarks": [landmark.model_dump() for landmark in landmarks],
            "panels": [Panel(id="door", corners_mm=DOOR_MM).model_dump()],
        }
    )


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


def scene_atlas(asset_id: str = "home-cabinet") -> Atlas:
    """The atlas of the synthetic scene, every point where it truly is."""

    def vec(point: np.ndarray) -> Vec3:
        return (float(point[0]), float(point[1]), float(point[2]))

    return Atlas(
        asset_id=asset_id,
        version="1",
        frame="board:rig_board_a",
        landmarks=[
            Landmark(id=point_id, position_mm=vec(point), sigma_mm=1.0)
            for point_id, point in POINTS_MM.items()
            if point_id != TARGET_ID
        ],
        target=Target(
            id=TARGET_ID, position_mm=vec(POINTS_MM[TARGET_ID]), sigma_mm=5.0, extent_mm=EXTENT_MM
        ),
    )
