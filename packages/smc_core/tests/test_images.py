from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from smc_core.images import read_images

# Smallest valid EXIF block: a TIFF header and one tag, Orientation = 6
# ("rotate 90 degrees for display"), which is what a phone held upright writes.
EXIF_ROTATE_90 = np.frombuffer(
    b"MM\x00\x2a\x00\x00\x00\x08"
    b"\x00\x01"
    b"\x01\x12\x00\x03\x00\x00\x00\x01\x00\x06\x00\x00"
    b"\x00\x00\x00\x00",
    np.uint8,
)


def test_read_images_yields_images_sorted_by_name(tmp_path: Path) -> None:
    image = np.zeros((30, 40, 3), np.uint8)
    cv.imwrite(tmp_path / "b.png", image)
    cv.imwrite(tmp_path / "a.jpg", image)
    (tmp_path / "notes.txt").write_text("not an image")

    images = list(read_images(tmp_path))

    assert [name for name, _ in images] == ["a.jpg", "b.png"]
    assert all(img.shape == (30, 40, 3) for _, img in images)


def test_read_images_keeps_the_sensor_pixel_grid(tmp_path: Path) -> None:
    image = np.zeros((30, 40, 3), np.uint8)
    cv.imwriteWithMetadata(
        tmp_path / "upright.jpg", image, [cv.IMAGE_METADATA_EXIF], [EXIF_ROTATE_90]
    )

    _, loaded = next(read_images(tmp_path))

    assert loaded.shape == (30, 40, 3)


def test_read_images_fails_on_an_unreadable_image(tmp_path: Path) -> None:
    (tmp_path / "broken.jpg").write_bytes(b"not a jpeg")

    with pytest.raises(OSError, match="cannot read image"):
        list(read_images(tmp_path))
