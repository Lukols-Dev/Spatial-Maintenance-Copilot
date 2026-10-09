"""View set images as the web app fetches them: the file itself, or a JPEG thumbnail.

The Locate page shows every viewpoint of a set as a small picture. A 1080x1920
PNG weighs megabytes; a 240 px wide JPEG, tens of kilobytes. Every answer has
an entity tag made from the file's modification time and size and the width
served, so a browser that revalidates gets a 304 until the file changes, and
nothing is decoded or sent again.
"""

import os
from pathlib import Path

import cv2 as cv

from smc_perception.errors import Conflict
from smc_perception.image_headers import read_header

MIN_WIDTH, MAX_WIDTH = 16, 2048
JPEG_QUALITY = 85


def thumbnail_width(path: Path, width: int | None) -> int | None:
    """The width to scale the image at path to, or None to serve the file itself.

    A thumbnail is never wider than its image: asking for that width or more
    gets the original bytes.
    """
    if width is None:
        return None
    header = read_header(path)
    if header.width is None:
        raise Conflict(f"no thumbnail of {path.name}: {header.error}")
    return width if width < header.width else None


def entity_tag(status: os.stat_result, width: int | None) -> str:
    """Changes with the file, and tells the file and each width of thumbnail apart."""
    served = "full" if width is None else f"w{width}"
    return f'"{status.st_mtime_ns:x}-{status.st_size:x}-{served}"'


def is_cached(if_none_match: str | None, tag: str) -> bool:
    """Whether an If-None-Match header names tag: the client holds this answer already."""
    if if_none_match is None:
        return False
    tags = {candidate.strip().removeprefix("W/") for candidate in if_none_match.split(",")}
    return "*" in tags or tag in tags


def thumbnail(path: Path, width: int) -> bytes:
    """The image scaled down to width, aspect kept, as a JPEG.

    It is read in the sensor grid, EXIF orientation ignored, so the thumbnail
    is turned the way the clicks and the poses are measured.
    """
    image = cv.imread(str(path), cv.IMREAD_COLOR | cv.IMREAD_IGNORE_ORIENTATION)
    if image is None:
        raise Conflict(f"cannot decode {path.name}")
    height = max(1, round(image.shape[0] * width / image.shape[1]))
    small = cv.resize(image, (width, height), interpolation=cv.INTER_AREA)
    encoded, data = cv.imencode(".jpg", small, [cv.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not encoded:
        raise Conflict(f"cannot encode a thumbnail of {path.name}")
    return data.tobytes()
