from collections.abc import Iterable, Iterator
from pathlib import Path

import cv2 as cv
import numpy as np


def read_video_frames(path: Path, step: int = 1) -> Iterator[tuple[str, np.ndarray]]:
    """Yield (label, frame) for every `step`-th frame of a video file.

    The label is the frame's position in the video, for example "frame_000120",
    so a view listed in a calibration report can be found again in the recording.

    Frames come out the way a player shows them: the rotation stored in the
    file is applied, so a phone held upright gives 1080x1920 frames. Record
    everything that shares one calibration in the same orientation.
    """
    if step < 1:
        raise ValueError("step must be at least 1")

    if not path.is_file():
        raise FileNotFoundError(f"no such video file: {path}")

    capture = cv.VideoCapture(path, cv.CAP_FFMPEG)
    if not capture.isOpened():
        raise OSError(f"cannot open video: {path}")

    try:
        index = 0
        while capture.grab():
            if index % step == 0:
                ok, frame = capture.retrieve()
                if ok:
                    yield f"frame_{index:06d}", frame
            index += 1
    finally:
        capture.release()


def sharpness(frame: np.ndarray) -> float:
    """Variance of the Laplacian of a BGR frame. Higher means sharper.

    The value depends on resolution and on what is in the picture, so it has
    no meaning on its own. Use it only to rank frames of the same scene.
    """
    gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
    return float(cv.Laplacian(gray, cv.CV_64F).var())


def sharpest_per_window(
    frames: Iterable[tuple[str, np.ndarray]], window: int
) -> Iterator[tuple[str, np.ndarray]]:
    """From every `window` consecutive frames yield only the sharpest one.

    Neighbouring frames show almost the same scene, so the sharpest of them is
    the one with the least motion blur. No threshold is involved.
    """
    if window < 1:
        raise ValueError("window must be at least 1")

    best: tuple[float, str, np.ndarray] | None = None
    for count, (label, frame) in enumerate(frames, start=1):
        score = sharpness(frame)
        if best is None or score > best[0]:
            best = (score, label, frame)
        if count % window == 0:
            yield best[1], best[2]
            best = None

    if best is not None:
        yield best[1], best[2]
