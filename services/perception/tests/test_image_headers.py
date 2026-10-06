from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from smc_perception.image_headers import ImageHeader, read_header
from workspace_builder import write_image


@pytest.mark.parametrize("name", ["a.png", "a.jpg", "a.JPEG"])
def test_the_size_comes_from_the_header(tmp_path: Path, name: str) -> None:
    path = write_image(tmp_path / name, 1080, 1920)

    assert read_header(path) == ImageHeader(1080, 1920, None)


def test_a_jpeg_with_exif_is_sized_in_its_sensor_grid(tmp_path: Path) -> None:
    path = write_image(tmp_path / "upright.jpg", 40, 30, exif=True)

    assert read_header(path) == ImageHeader(40, 30, None)


def test_a_progressive_jpeg_is_sized_too(tmp_path: Path) -> None:
    path = tmp_path / "progressive.jpg"
    cv.imwrite(str(path), np.zeros((30, 40, 3), np.uint8), [cv.IMWRITE_JPEG_PROGRESSIVE, 1])

    assert read_header(path) == ImageHeader(40, 30, None)


@pytest.mark.parametrize(
    ("name", "content", "error"),
    [
        ("a.png", b"\xff\xd8\xff\xe0", "not a PNG file"),
        ("a.jpg", b"\x89PNG\r\n\x1a\n", "not a JPEG file"),
        ("a.jpg", b"\xff\xd8\xff\xe1\x00\x10exif", "broken JPEG: it ends before its frame header"),
        (
            "a.jpg",
            b"\xff\xd8\xff\xda\x00\x02",
            "broken JPEG: no frame header before the image data",
        ),
        ("a.png", b"", "not a PNG file"),
    ],
)
def test_a_broken_file_gives_a_reason(
    tmp_path: Path, name: str, content: bytes, error: str
) -> None:
    path = tmp_path / name
    path.write_bytes(content)

    assert read_header(path) == ImageHeader(None, None, error)


def test_a_changed_file_is_read_again(tmp_path: Path) -> None:
    path = write_image(tmp_path / "a.png", 40, 30)
    assert read_header(path).width == 40

    write_image(path, 400, 300)

    assert read_header(path).width == 400


def test_a_missing_file_gives_a_reason(tmp_path: Path) -> None:
    assert read_header(tmp_path / "gone.png").error == "cannot read the file"
