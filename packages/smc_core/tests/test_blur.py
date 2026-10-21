"""A frame's blur, measured on its printed markers: the width of their edges.

The frames are the synthetic marked scene's, drawn sharp, then smeared the way
a camera moving during the exposure smears them: averaged along a line.
"""

import cv2 as cv
import numpy as np
import pytest
from smc_core.blur import edge_width, frame_quality
from smc_core.markers import MarkerSet, detect, marker_detector
from smc_core.testing import MARKER_SIDE_MM, MARKERS_MM, TAG_ID, rendered_marker_views, rig_board

MARKERS = MarkerSet(cv.aruco.DICT_5X5_100, tuple(range(50, 61)), TAG_ID, MARKER_SIDE_MM)


@pytest.fixture(scope="module")
def frames() -> list[np.ndarray]:
    return [frame for _, frame in rendered_marker_views(rig_board(), MARKERS_MM)]


def smeared(frame: np.ndarray, length: int, angle_deg: float) -> np.ndarray:
    """The frame as a camera moving `length` pixels along angle_deg during the exposure takes it."""
    kernel = np.zeros((length, length), np.float32)
    kernel[length // 2, :] = 1
    centre = ((length - 1) / 2, (length - 1) / 2)
    turned = cv.warpAffine(kernel, cv.getRotationMatrix2D(centre, angle_deg, 1.0), (length, length))
    return cv.filter2D(frame, -1, turned / turned.sum())


def quads(frame: np.ndarray) -> tuple[np.ndarray, ...]:
    return detect(marker_detector(MARKERS), MARKERS, frame).quads


def test_a_sharp_frame_has_edges_a_few_pixels_wide(frames: list[np.ndarray]) -> None:
    for frame in frames:
        quality = frame_quality(frame, quads(frame))

        assert quality.markers >= 5
        assert quality.edge_width_px == pytest.approx(2.83, abs=0.1)


@pytest.mark.parametrize("angle", [0.0, 30.0, 45.0, 90.0, 135.0])
def test_motion_widens_the_edges_by_its_length_in_any_direction(
    frames: list[np.ndarray], angle: float
) -> None:
    frame = frames[0]
    found = quads(frame)

    widths = [
        frame_quality(smeared(frame, length, angle), found).edge_width_px for length in (5, 9, 15)
    ]

    # Between two measured directions a motion reads a little short of its length.
    assert widths == sorted(widths)
    assert widths[1] == pytest.approx(9, rel=0.15)
    assert widths[2] == pytest.approx(15, rel=0.15)


def test_the_width_does_not_follow_the_markers_size_or_the_light(
    frames: list[np.ndarray],
) -> None:
    near, far = frames[0], frames[-1]
    dim = (near.astype(np.float32) * 0.4 + 30).astype(np.uint8)

    widths = [
        frame_quality(smeared(frame, 9, 0.0), quads(frame)).edge_width_px
        for frame in (near, far, dim)
    ]

    assert max(widths) - min(widths) < 0.6  # type: ignore[operator]


def test_markers_still_found_in_a_smeared_frame_measure_it(frames: list[np.ndarray]) -> None:
    blurred = smeared(frames[0], 9, 0.0)

    quality = frame_quality(blurred, quads(blurred))

    assert quality.markers > 0
    assert quality.edge_width_px == pytest.approx(9, abs=1.0)


def test_a_frame_without_markers_has_no_width() -> None:
    blank = np.full((1920, 1080, 3), 200, np.uint8)

    assert frame_quality(blank, quads(blank)).model_dump() == {"markers": 0, "edge_width_px": None}


def test_a_flat_or_tiny_box_is_not_measured() -> None:
    flat = np.full((200, 200), 128, np.uint8)
    corners = np.array([[50, 50], [150, 50], [150, 150], [50, 150]], np.float32)

    assert edge_width(flat, corners) is None
    assert edge_width(flat, np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32)) is None
