"""The motion thresholds' evidence: a small grey picture's change against the markers' motion, on a video."""

from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from motion_limit import main, rank_correlation, sample
from smc_core.testing import MARKERS_MM, TAG_ID, rendered_marker_views, rig_board

REPOSITORY = Path(__file__).resolve().parents[1]
WITHOUT_TAG = {marker: corners for marker, corners in MARKERS_MM.items() if marker != TAG_ID}


def test_a_frame_is_sampled_small_and_grey_with_its_aspect() -> None:
    frame = np.zeros((1920, 1080, 3), np.uint8)

    assert sample(frame).shape == (160, 90)
    assert rank_correlation(
        np.array([1.0, 2.0, 3.0]), np.array([10.0, 30.0, 20.0])
    ) == pytest.approx(0.5)


@pytest.fixture
def video(tmp_path: Path) -> Path:
    """The synthetic marked scene held still for six frames, then panned 16 px a frame."""
    _, frame = next(iter(rendered_marker_views(rig_board(), WITHOUT_TAG)))
    frame = cv.cvtColor(frame, cv.COLOR_GRAY2BGR) if frame.ndim == 2 else frame
    height, width = frame.shape[:2]
    path = tmp_path / "pan.avi"
    writer = cv.VideoWriter(str(path), cv.VideoWriter.fourcc(*"MJPG"), 30.0, (width, height))
    for step in [0] * 6 + list(range(1, 7)):
        shift = np.float32([[1, 0, 16 * step], [0, 1, 0]])
        writer.write(cv.warpAffine(frame, shift, (width, height), borderValue=(255, 255, 255)))
    writer.release()
    return path


def test_the_still_frames_stay_below_and_the_panned_ones_go_above(
    video: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main([str(video), "--rig", str(REPOSITORY / "calib" / "rig.yaml")])

    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == "11 pairs of consecutive frames with markers in 1 videos"
    assert "markers under 4 px: 5 pairs, 100% below 2.5" in printed
    assert "markers 8 px or more: 6 pairs, 100% above 3.5" in printed
