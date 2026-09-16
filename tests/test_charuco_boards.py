"""Verification of the printable ChArUco rig boards.

These boards are measurement hardware. Once a sheet is printed, bonded to a
rigid substrate and measured with calipers, a mistake in the dictionary, the ID
ranges or the marker-to-square clearance costs a full print-bond-measure cycle
to discover, and it surfaces as a bad calibration RMS rather than as an error.

Every check here reads its parameters from `board_specs()` in the generator, so
a test can never pass against a rig that differs from the one sent to the
printer.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from gen_charuco_boards import (
    DICT_BITS,
    board_specs,
    get_dictionary,
    make_board,
)

# Detection-only rendering. Coarser than the print raster on purpose: this
# exercises board construction, not print resolution.
PX_PER_SQUARE = 160
MARGIN_PX = 40
BORDER_BITS = 1

SPECS = board_specs()
SPEC_IDS = [s["key"] for s in SPECS]


def _render_for_detection(board, spec) -> np.ndarray:
    """Render the board with a quiet zone around it.

    The print pages carry no margin because the white of the A4 sheet provides
    it. A bare render has markers flush against the image border, where they
    cannot be decoded, so the margin has to be added back here.
    """
    width = spec["squares_x"] * PX_PER_SQUARE + 2 * MARGIN_PX
    height = spec["squares_y"] * PX_PER_SQUARE + 2 * MARGIN_PX
    return board.generateImage((width, height), marginSize=MARGIN_PX, borderBits=BORDER_BITS)


def _detect(board, image):
    """Run the ChArUco detector the way the calibration pipeline will.

    Marker corner refinement is disabled deliberately. The OpenCV docs advise
    against it for ChArUco: with chessboard squares this close, the sub-pixel
    step can shift marker corners enough to spoil the interpolation of the
    ChArUco corners, which are the points calibration actually consumes. The
    corners get their own sub-pixel refinement after interpolation.
    """
    detector_params = cv2.aruco.DetectorParameters()
    detector_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_NONE
    detector = cv2.aruco.CharucoDetector(board, cv2.aruco.CharucoParameters(), detector_params)
    charuco_corners, charuco_ids, marker_corners, marker_ids = detector.detectBoard(image)
    return charuco_corners, charuco_ids, marker_corners, marker_ids


@pytest.fixture(params=SPECS, ids=SPEC_IDS)
def spec(request):
    return request.param


@pytest.fixture
def detection(spec):
    board, _ = make_board(
        spec["squares_x"],
        spec["squares_y"],
        spec["square_mm"],
        spec["marker_mm"],
        get_dictionary(),
        spec["ids"],
    )
    image = _render_for_detection(board, spec)
    return _detect(board, image)


def test_every_marker_is_decoded(spec, detection) -> None:
    _, _, _, marker_ids = detection
    found = 0 if marker_ids is None else len(marker_ids)
    assert found == len(spec["ids"]), f"decoded {found} markers, board defines {len(spec['ids'])}"


def test_decoded_ids_match_the_specification(spec, detection) -> None:
    _, _, _, marker_ids = detection
    assert marker_ids is not None, "no markers decoded at all"
    found = sorted(int(i) for i in marker_ids.flatten())
    assert found == spec["ids"], (
        "decoded IDs differ from the specification; "
        "check the dictionary and the ID range in board_specs()"
    )


def test_all_charuco_corners_are_interpolated(spec, detection) -> None:
    """The corner count is the check that matters.

    ChArUco corners are the chessboard saddle points, and a corner is returned
    only when both of its neighbouring markers were decoded. One marker lost
    therefore removes several corners, so this count catches degradation that a
    marker tally alone would hide.
    """
    _, charuco_ids, _, _ = detection
    expected = (spec["squares_x"] - 1) * (spec["squares_y"] - 1)
    found = 0 if charuco_ids is None else len(charuco_ids)
    assert found == expected, f"interpolated {found} corners, board has {expected}"


def test_marker_clearance_respects_the_opencv_rule(spec) -> None:
    """Keep the white gap around each marker above the documented minimum.

    OpenCV requires the gap between a chessboard square and the marker inside it
    to exceed 70% of one marker module. Below that, corner interpolation
    degrades on real photographs even though the rendered board looks correct
    and detects perfectly in this synthetic test.
    """
    modules_across = DICT_BITS + 2 * BORDER_BITS
    module_mm = spec["marker_mm"] / modules_across
    gap_mm = (spec["square_mm"] - spec["marker_mm"]) / 2
    minimum_mm = 0.7 * module_mm
    assert gap_mm > minimum_mm, (
        f"clearance {gap_mm:.2f} mm is below the {minimum_mm:.2f} mm minimum; lower MARKER_RATIO"
    )


def test_id_count_fills_the_board(spec) -> None:
    capacity = (spec["squares_x"] * spec["squares_y"]) // 2
    assert len(spec["ids"]) == capacity


def test_id_ranges_are_disjoint_across_boards() -> None:
    """Two boards sharing an ID are indistinguishable once both are in frame.

    The rig is photographed with several boards visible at once, so a collision
    here does not fail loudly: it produces a plausible pose computed from
    landmarks belonging to the wrong board.
    """
    seen: dict[int, str] = {}
    for s in SPECS:
        for marker_id in s["ids"]:
            assert marker_id not in seen, (
                f"ID {marker_id} used by both {seen.get(marker_id)} and {s['key']}"
            )
            seen[marker_id] = s["key"]
