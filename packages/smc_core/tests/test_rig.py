from pathlib import Path

import cv2 as cv
import pytest
from smc_core.rig import load_rig_board

RIG = """\
dictionary: DICT_5X5_100
marker_ratio: 0.72
boards:
  fully_measured:
    squares_x: 5
    squares_y: 7
    ids: [0, 16] # inclusive range
    square_nominal_mm: 30.0
    marker_nominal_mm: 21.6
    square_measured_mm: 29.85
    marker_measured_mm: 21.5
    measurement_uncertainty_mm: 0.25
  square_measured:
    squares_x: 4
    squares_y: 6
    ids: [20, 31] # inclusive range
    square_nominal_mm: 25.0
    marker_nominal_mm: 18.0
    square_measured_mm: 24.9
    marker_measured_mm: null
    measurement_uncertainty_mm: null
  unmeasured:
    squares_x: 4
    squares_y: 6
    ids: [35, 46] # inclusive range
    square_nominal_mm: 25.0
    marker_nominal_mm: 18.0
    square_measured_mm: null
    marker_measured_mm: null
    measurement_uncertainty_mm: null
"""


@pytest.fixture
def rig_file(tmp_path: Path) -> Path:
    path = tmp_path / "rig.yaml"
    path.write_text(RIG, encoding="utf-8")
    return path


def test_load_rig_board_reads_the_caliper_measurements(rig_file: Path) -> None:
    board = load_rig_board(rig_file, "fully_measured")

    assert (board["squares_x"], board["squares_y"]) == (5, 7)
    assert board["square_mm"] == 29.85
    assert board["marker_mm"] == 21.5
    assert board["dictionary_id"] == cv.aruco.DICT_5X5_100
    assert board["marker_ids"] == list(range(17))
    assert board["measurement_uncertainty_mm"] == 0.25


def test_load_rig_board_scales_an_unmeasured_marker_with_the_square(rig_file: Path) -> None:
    board = load_rig_board(rig_file, "square_measured")

    assert board["marker_mm"] == pytest.approx(24.9 * 18.0 / 25.0)
    assert board["marker_ids"] == list(range(20, 32))
    assert board["measurement_uncertainty_mm"] is None


def test_load_rig_board_refuses_a_board_without_a_measured_square(rig_file: Path) -> None:
    with pytest.raises(ValueError, match="square_measured_mm"):
        load_rig_board(rig_file, "unmeasured")


def test_load_rig_board_names_a_missing_board(rig_file: Path) -> None:
    with pytest.raises(ValueError, match="no board named 'missing'"):
        load_rig_board(rig_file, "missing")
