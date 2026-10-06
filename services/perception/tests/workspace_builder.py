"""Files of a workspace, written the way the tools and the annotator write them."""

from pathlib import Path

import cv2 as cv
import numpy as np
from smc_core.calibration import save_calibration
from smc_core.contracts import Clicks
from smc_core.testing import (
    CAMERA_ID,
    INTRINSICS,
    POINTS_MM,
    calibration,
    clicks_for,
    rendered_views,
    rig_board,
)

# calib/rig.yaml as gen_charuco_boards.py wrote it, with the calibration board
# measured. rig_board_a is the board of smc_core.testing.
RIG_YAML = """\
# Nominal geometry emitted by gen_charuco_boards.py.
# Replace every *_measured_mm value with a caliper reading from the
# printed and mounted board before any pose is computed.
dictionary: DICT_5X5_100
marker_ratio: 0.72
boards:
  calibration_board:
    squares_x: 5
    squares_y: 7
    ids: [0, 16] # inclusive range
    square_nominal_mm: 30.0
    marker_nominal_mm: 21.6
    square_measured_mm: 30.0
    marker_measured_mm: null
    measurement_uncertainty_mm: 0.25
    substrate: "A4 print taped with masking tape to paperboard"
    measured_on: 2026-09-17
  rig_board_a:
    squares_x: 4
    squares_y: 6
    ids: [20, 31] # inclusive range
    square_nominal_mm: 25.0
    marker_nominal_mm: 18.0
    square_measured_mm: null
    marker_measured_mm: null
    measurement_uncertainty_mm: null
    substrate: null
    measured_on: null
  rig_board_b:
    squares_x: 4
    squares_y: 6
    ids: [35, 46] # inclusive range
    square_nominal_mm: 25.0
    marker_nominal_mm: 18.0
    square_measured_mm: null
    marker_measured_mm: null
    measurement_uncertainty_mm: null
    substrate: null
    measured_on: null
"""

# The smallest valid EXIF block: a TIFF header and Orientation = 6 ("rotate 90
# degrees for display"), what a phone held upright writes.
EXIF_ROTATE_90 = np.frombuffer(
    b"MM\x00\x2a\x00\x00\x00\x08"
    b"\x00\x01"
    b"\x01\x12\x00\x03\x00\x00\x00\x01\x00\x06\x00\x00"
    b"\x00\x00\x00\x00",
    np.uint8,
)


def write_calibration(
    root: Path, file: str = "phone.yml", size: tuple[int, int] | None = None
) -> Path:
    """The synthetic phone's calibration, as calibrate_camera.py saves it."""
    path = root / "calib" / "intrinsics" / file
    path.parent.mkdir(parents=True, exist_ok=True)
    save_calibration(str(path), calibration(), size or INTRINSICS["image_size"], CAMERA_ID)
    return path


def write_rig(root: Path, text: str = RIG_YAML) -> Path:
    path = root / "calib" / "rig.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def write_image(path: Path, width: int, height: int, exif: bool = False) -> Path:
    """A grey image; with exif, a JPEG tagged to be shown rotated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((height, width, 3), 128, np.uint8)
    if exif:
        assert cv.imwriteWithMetadata(path, image, [cv.IMAGE_METADATA_EXIF], [EXIF_ROTATE_90])
    else:
        assert cv.imwrite(str(path), image)
    return path


def write_view_set(root: Path, name: str, images: dict[str, tuple[int, int]]) -> Path:
    folder = root / "data" / "views" / name
    folder.mkdir(parents=True, exist_ok=True)
    for file, (width, height) in images.items():
        write_image(folder / file, width, height)
    return folder


def write_scene(root: Path, name: str = "cabinet") -> Path:
    """A view set of the synthetic scene, clicked by the annotator: the input of an atlas."""
    folder = root / "data" / "views" / name
    folder.mkdir(parents=True, exist_ok=True)
    for file, frame in rendered_views(rig_board()):
        cv.imwrite(str(folder / file), frame)
    (folder / "clicks.json").write_text(annotated(clicks_for(1.0)).model_dump_json(indent=2) + "\n")
    return folder


def annotated(clicks: Clicks) -> Clicks:
    """The clicks as the annotator saves them, with its list of points."""
    return Clicks(camera_id=clicks.camera_id, points=list(POINTS_MM), views=clicks.views)
