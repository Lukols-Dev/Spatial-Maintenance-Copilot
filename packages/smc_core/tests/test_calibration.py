import cv2 as cv
import numpy as np
import pytest
from smc_core.calibration import create_board, detect_board


@pytest.fixture
def board() -> cv.aruco.CharucoBoard:
    """The printed calibration board: 5x7 squares of 30 mm, markers 21.6 mm."""
    return create_board(5, 7, 30.0, 21.6, cv.aruco.DICT_5X5_100, list(range(17)))


def test_create_board_matches_printed_board(board: cv.aruco.CharucoBoard) -> None:
    assert board.getChessboardSize() == (5, 7)
    assert len(board.getIds()) == 17

    corners = board.getChessboardCorners()
    assert corners.shape == (24, 3)
    np.testing.assert_allclose(corners[0], [30.0, 30.0, 0.0])
    np.testing.assert_allclose(corners[-1], [120.0, 180.0, 0.0])


def test_detect_board_finds_every_corner(board: cv.aruco.CharucoBoard) -> None:
    # 100 px per square plus a 40 px white margin: a marker touching the image
    # edge cannot be decoded.
    image = board.generateImage((580, 780), marginSize=40)
    detector = cv.aruco.CharucoDetector(board)

    charuco_corners, charuco_ids, _, marker_ids = detect_board(detector, image)

    assert charuco_corners.shape == (24, 2)
    assert sorted(charuco_ids.tolist()) == list(range(24))
    assert len(marker_ids) == 17


def test_detect_board_returns_empty_arrays_when_nothing_found(
    board: cv.aruco.CharucoBoard,
) -> None:
    blank = np.full((780, 580), 255, np.uint8)
    detector = cv.aruco.CharucoDetector(board)

    charuco_corners, charuco_ids, _, marker_ids = detect_board(detector, blank)

    assert charuco_corners.shape == (0, 2)
    assert len(charuco_ids) == 0
    assert len(marker_ids) == 0
