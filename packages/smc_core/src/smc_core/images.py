from collections.abc import Iterator
from pathlib import Path

import cv2 as cv
import numpy as np

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def read_images(folder: Path) -> Iterator[tuple[str, np.ndarray]]:
    """Yield (file name, image) for every JPEG or PNG in the folder, sorted by name.

    Images are read one at a time, so a folder of 12 MP photos never sits in
    memory at once.

    EXIF orientation is ignored on purpose. A phone stores every photo in the
    sensor's pixel grid and only tags how the phone was held. Camera intrinsics
    describe that grid, so the pixels must not be rotated on load.
    """
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue

        image = cv.imread(path, cv.IMREAD_COLOR | cv.IMREAD_IGNORE_ORIENTATION)
        if image is None:
            raise OSError(f"cannot read image: {path}")

        yield path.name, image
