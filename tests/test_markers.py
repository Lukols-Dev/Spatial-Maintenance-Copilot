"""The printable landmark markers: each decodes to its own ID, and none is a board's.

A marker that collides with a board, or one too small to decode, is found only
after printing, sticking and recording a session; these checks find it first.
"""

import re
from pathlib import Path

import cv2
import numpy as np
import pytest
from gen_charuco_boards import board_specs, get_dictionary
from gen_markers import (
    CELL_W_MM,
    COLUMNS,
    FOOTER_TOP_MM,
    LABEL_BELOW_MM,
    LANDMARK_IDS,
    MARKER_MM,
    QUIET_MM,
    ROWS,
    TARGET_ID,
    cell_origin,
    main,
    marker_ids,
    render_marker,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from smc_core.markers import load_marker_set


def test_no_marker_is_a_board_s() -> None:
    board_ids = {marker for spec in board_specs() for marker in spec["ids"]}

    assert not board_ids & set(marker_ids())
    assert len(set(marker_ids())) == len(marker_ids()) == len(LANDMARK_IDS) + 1
    assert TARGET_ID not in LANDMARK_IDS


@pytest.mark.parametrize("marker_id", marker_ids())
def test_each_marker_decodes_to_its_own_id(marker_id: int) -> None:
    dictionary = get_dictionary()
    image = cv2.copyMakeBorder(
        render_marker(dictionary, marker_id, 140), 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255
    )

    _, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(image)

    assert ids is not None and ids.ravel().tolist() == [marker_id]


def test_the_quiet_zone_holds_at_least_one_module() -> None:
    assert QUIET_MM >= MARKER_MM / 7


def test_every_cell_fits_on_the_page_inside_its_margins() -> None:
    assert len(marker_ids()) <= COLUMNS * ROWS
    page_w_mm, page_h_mm = A4[0] / mm, A4[1] / mm
    for index in range(len(marker_ids())):
        x, y = cell_origin(index)
        assert x >= 10 and x + CELL_W_MM <= page_w_mm - 10
        assert y - LABEL_BELOW_MM >= FOOTER_TOP_MM and y + CELL_W_MM <= page_h_mm - 15


def test_the_sheet_is_one_page_of_every_marker(tmp_path: Path) -> None:
    out = tmp_path / "markers.pdf"

    main(["--out", str(out)])

    pdf = out.read_bytes()
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page(?!s)", pdf)) == 1
    assert pdf.count(b"/Subtype /Image") == len(marker_ids())


def test_a_rendered_marker_is_black_bordered() -> None:
    image = render_marker(get_dictionary(), LANDMARK_IDS[0], 70)

    assert image.shape == (70, 70)
    assert np.all(image[:10, :] == 0) and np.all(image[:, :10] == 0)


def test_the_sheet_prints_the_markers_the_rig_file_names() -> None:
    markers = load_marker_set(Path(__file__).resolve().parents[1] / "calib" / "rig.yaml")

    assert list(markers.landmark_ids) == LANDMARK_IDS
    assert markers.target_id == TARGET_ID
    assert markers.side_mm == MARKER_MM
