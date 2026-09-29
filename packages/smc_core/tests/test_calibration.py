import cv2 as cv
import numpy as np
from smc_core.calibration import create_board


def test_create_board_matches_printed_board() -> None:
    board = create_board(5, 7, 30.0, 21.6, cv.aruco.DICT_5X5_100, list(range(17)))

    assert board.getChessboardSize() == (5, 7)
    assert len(board.getIds()) == 17

    corners = board.getChessboardCorners()
    assert corners.shape == (24, 3)
    np.testing.assert_allclose(corners[0], [30.0, 30.0, 0.0])
    np.testing.assert_allclose(corners[-1], [120.0, 180.0, 0.0])
