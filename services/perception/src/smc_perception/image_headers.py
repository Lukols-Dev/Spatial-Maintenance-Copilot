"""Image sizes read from file headers, without decoding any pixels.

GET /workspace sizes every image of every view set. Decoding a 1080x1920 PNG
takes tens of milliseconds; its size sits in the first 24 bytes. A JPEG's
size is in its frame header, after the EXIF block, and is the sensor grid:
the EXIF orientation is ignored, as the pipeline ignores it.
"""

import os
import struct
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Literal, NamedTuple

ImageFormat = Literal["png", "jpeg"]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Start-of-frame markers, the ones that carry the size: C0 to CF without DHT
# (C4), JPG (C8) and DAC (CC).
SOF_MARKERS = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
# Markers without a length field: TEM, RST0 to RST7 and SOI.
STANDALONE_MARKERS = {0x01, *range(0xD0, 0xD9)}
START_OF_SCAN = 0xDA
END_OF_IMAGE = 0xD9


class ImageHeader(NamedTuple):
    width: int | None
    height: int | None
    error: str | None


def image_format(name: str) -> ImageFormat:
    """The format a file name declares; the header must agree with it."""
    return "png" if name.lower().endswith(".png") else "jpeg"


def read_header(path: Path) -> ImageHeader:
    """Size of a PNG or JPEG file, or why it cannot be read. Never raises.

    Results are kept per (path, modification time, size), so an image is read
    once until it changes.
    """
    try:
        status = path.stat()
    except OSError:
        return ImageHeader(None, None, "cannot read the file")
    return _cached_header(str(path), status.st_mtime_ns, status.st_size)


@lru_cache(maxsize=8192)
def _cached_header(path: str, _mtime_ns: int, _size: int) -> ImageHeader:
    try:
        with open(path, "rb") as file:
            if image_format(path) == "png":
                width, height = _png_size(file)
            else:
                width, height = _jpeg_size(file)
    except OSError:
        return ImageHeader(None, None, "cannot read the file")
    except ValueError as error:
        return ImageHeader(None, None, str(error))
    if width == 0 or height == 0:
        return ImageHeader(None, None, "the header gives no size")
    return ImageHeader(width, height, None)


def _png_size(file: BinaryIO) -> tuple[int, int]:
    head = file.read(24)
    if len(head) < 24 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def _jpeg_size(file: BinaryIO) -> tuple[int, int]:
    """Walk the segments up to the frame header, skipping EXIF and the rest."""
    if file.read(2) != b"\xff\xd8":
        raise ValueError("not a JPEG file")
    while True:
        start = file.read(1)
        if start != b"\xff":
            if not start:
                raise ValueError("broken JPEG: it ends before its frame header")
            raise ValueError("broken JPEG: a segment does not start with a marker")
        marker = file.read(1)
        while marker == b"\xff":  # fill bytes may pad a marker
            marker = file.read(1)
        if not marker:
            raise ValueError("broken JPEG: it ends before its frame header")
        code = marker[0]
        if code in STANDALONE_MARKERS:
            continue
        if code in (END_OF_IMAGE, START_OF_SCAN):
            raise ValueError("broken JPEG: no frame header before the image data")
        length_bytes = file.read(2)
        if len(length_bytes) < 2:
            raise ValueError("broken JPEG: it ends before its frame header")
        (length,) = struct.unpack(">H", length_bytes)
        if length < 2:
            raise ValueError("broken JPEG: a segment has a wrong length")
        if code in SOF_MARKERS:
            frame = file.read(5)
            if len(frame) < 5:
                raise ValueError("broken JPEG: its frame header is cut short")
            height, width = struct.unpack(">HH", frame[1:5])
            return width, height
        file.seek(length - 2, os.SEEK_CUR)
