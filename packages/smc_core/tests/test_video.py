from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from smc_core.video import read_video_frames, sharpest_per_window, sharpness


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
    assert [round(frame.mean() / 20) for _, frame in frames] == [0, 3, 6, 9]


def test_read_video_frames_fails_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no such video file"):
        list(read_video_frames(tmp_path / "missing.mov"))


def test_read_video_frames_fails_on_a_file_that_is_not_a_video(tmp_path: Path) -> None:
    fake = tmp_path / "notes.mov"
    fake.write_text("not a video")

    with pytest.raises(OSError, match="cannot open video"):
        list(read_video_frames(fake))


def checkerboard() -> np.ndarray:
    """A 64x64 BGR image of sharp black and white squares."""
    tile = np.kron([[0, 255], [255, 0]], np.ones((16, 16)))
    return cv.cvtColor(np.tile(tile, (2, 2)).astype(np.uint8), cv.COLOR_GRAY2BGR)


def test_sharpness_ranks_a_blurred_frame_lower() -> None:
    sharp = checkerboard()
    blurred = cv.GaussianBlur(sharp, (0, 0), 3)

    assert sharpness(sharp) > sharpness(blurred)


def test_sharpest_per_window_keeps_one_frame_per_window() -> None:
    sharp = checkerboard()
    blurred = cv.GaussianBlur(sharp, (0, 0), 3)
    frames = [
        ("a", blurred),
        ("b", sharp),
        ("c", blurred),
        ("d", blurred),
        ("e", blurred),
        ("f", sharp),
        ("g", blurred),
    ]

    kept = [label for label, _ in sharpest_per_window(frames, window=3)]

    assert kept == ["b", "f", "g"]


def test_sharpest_per_window_never_chooses_a_frame_keep_refuses() -> None:
    """The sharpest frame of a window is refused, so the next sharpest is kept;
    a window whose every frame is refused gives nothing."""
    sharp = checkerboard()
    soft = cv.GaussianBlur(sharp, (0, 0), 1)
    blurred = cv.GaussianBlur(sharp, (0, 0), 3)
    refused = [sharp.copy() for _ in range(4)]
    frames = [
        ("a", blurred),
        ("b", refused[0]),
        ("c", soft),
        ("d", refused[1]),
        ("e", refused[2]),
        ("f", refused[3]),
        ("g", blurred),
    ]

    kept = sharpest_per_window(
        frames, window=3, keep=lambda frame: not any(frame is r for r in refused)
    )

    assert [label for label, _ in kept] == ["c", "g"]
