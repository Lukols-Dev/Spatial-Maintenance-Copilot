"""A stored calibration held against a new video of the board: the true model fits, a wrong one does not."""

from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from check_calibration import check_calibration, format_check
from smc_core.calibration import Intrinsics
from smc_core.testing import INTRINSICS, camera_pose, render, rig_board


@pytest.fixture(scope="module")
def video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The rig board from thirty viewpoints, as a clip of the calibrated camera.

    Eight leave the principal point loose by some 25 px; a calibration video
    has dozens of views, and thirty pin it to a few.
    """
    path = tmp_path_factory.mktemp("calibration") / "board.avi"
    writer = cv.VideoWriter(str(path), cv.VideoWriter.fourcc(*"MJPG"), 30.0, (1080, 1920))
    rng = np.random.default_rng(3)
    for _ in range(30):
        turn = [rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(-0.3, 0.3)]
        frame = render(rig_board(), *camera_pose(turn, rng.uniform(450.0, 750.0)))
        writer.write(cv.cvtColor(frame, cv.COLOR_GRAY2BGR))
    writer.release()
    return path


def scaled(intrinsics: Intrinsics, focal: float) -> Intrinsics:
    matrix = intrinsics["camera_matrix"].copy()
    matrix[0, 0] *= focal
    matrix[1, 1] *= focal
    return {**intrinsics, "camera_matrix": matrix}


def test_the_true_calibration_still_describes_the_camera(video: Path) -> None:
    check = check_calibration(video, INTRINSICS, rig_board(), step=1)

    assert check.views == 30
    assert check.stored_rms_px < 1.0
    assert check.fits
    assert "the stored calibration still describes the camera" in format_check(check)


def test_a_calibration_off_by_a_few_percent_no_longer_does(video: Path) -> None:
    check = check_calibration(video, scaled(INTRINSICS, 1.05), rig_board(), step=1)

    assert not check.fits
    assert any(misfit.startswith("fx has moved by -5.") for misfit in check.misfits)
    assert "no longer describes the camera" in format_check(check)


def test_a_video_of_another_size_is_refused(video: Path) -> None:
    other: Intrinsics = {**INTRINSICS, "image_size": (1920, 1080)}

    with pytest.raises(ValueError, match="calibrated at 1920x1080"):
        check_calibration(video, other, rig_board(), step=1)


def test_a_video_without_the_board_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "blank.avi"
    writer = cv.VideoWriter(str(path), cv.VideoWriter.fourcc(*"MJPG"), 30.0, (64, 48))
    writer.write(np.zeros((48, 64, 3), np.uint8))
    writer.release()

    with pytest.raises(ValueError, match="no frame"):
        check_calibration(path, INTRINSICS, rig_board(), step=1)
