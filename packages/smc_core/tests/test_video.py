from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from smc_core.video import read_video_frames


def write_clip(path: Path, frame_count: int) -> None:
    """Write a tiny video in which frame i is filled with brightness i * 20."""
    writer = cv.VideoWriter(path, cv.VideoWriter.fourcc(*"MJPG"), 30.0, (64, 48))
    for i in range(frame_count):
        writer.write(np.full((48, 64, 3), i * 20, np.uint8))
    writer.release()


def test_read_video_frames_yields_every_step_th_frame(tmp_path: Path) -> None:
    clip = tmp_path / "clip.avi"
    write_clip(clip, frame_count=10)

    frames = list(read_video_frames(clip, step=3))

    labels = [label for label, _ in frames]
    assert labels == ["frame_000000", "frame_000003", "frame_000006", "frame_000009"]
    assert all(frame.shape == (48, 64, 3) for _, frame in frames)
    # Frame i was written with brightness i * 20, so this checks that each
    # label belongs to the picture next to it.
    assert [round(frame.mean() / 20) for _, frame in frames] == [0, 3, 6, 9]


def test_read_video_frames_fails_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError, match="cannot open video"):
        list(read_video_frames(tmp_path / "missing.mov"))
