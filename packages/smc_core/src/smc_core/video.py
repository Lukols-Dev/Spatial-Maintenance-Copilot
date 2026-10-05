from collections.abc import Iterator
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
