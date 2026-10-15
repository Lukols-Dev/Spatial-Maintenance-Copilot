"""Printed ArUco markers as landmarks: found in every frame, with no click.

A landmark marker gives four landmarks, its corners, named m<id>_<corner>
with the corners in OpenCV's order: top-left, top-right, bottom-right and
bottom-left of the marker as printed. The target's tag gives the target's
point, the centre of the tag, and its four corners, <target>_<corner>, which
orient the target's box (atlas_build). Any other marker in the frame, those of
the rig boards among them, is not one of these and is left out.

Markers on a part that moves, a flap that opens, stand where the atlas has
them only while it is shut. The target's tag is in sight only when it is open,
so in a frame that shows the tag those markers are left out.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import cv2 as cv
import numpy as np
import yaml

from smc_core.contracts import Vec2


@dataclass(frozen=True)
class MarkerSet:
    """The markers of the rig file: which are landmarks, which is the target's tag."""

    dictionary_id: int
    landmark_ids: tuple[int, ...]
    target_id: int
    side_mm: float


@dataclass(frozen=True)
class Detection:
    """One frame's markers: every landmark corner by its id, and the target's tag if in sight."""

    landmarks: dict[str, Vec2]
    tag: tuple[Vec2, Vec2, Vec2, Vec2] | None


def load_marker_set(path: Path) -> MarkerSet:
    """The markers section of calib/rig.yaml."""
    with path.open(encoding="utf-8") as file:
        rig = yaml.safe_load(file)
    if "markers" not in rig:
        raise ValueError(f"{path}: no markers section")
    markers = rig["markers"]
    first, last = markers["landmark_ids"]  # inclusive range
    measured = markers.get("side_measured_mm")
    return MarkerSet(
        dictionary_id=getattr(cv.aruco, rig["dictionary"]),
        landmark_ids=tuple(range(first, last + 1)),
        target_id=int(markers["target_id"]),
        side_mm=float(measured if measured is not None else markers["side_nominal_mm"]),
    )


def landmark_id(marker_id: int, corner: int) -> str:
    return f"m{marker_id}_{corner}"


def tag_point_ids(target_id: str) -> list[str]:
    """The ids of the four corners of the target's tag, as the atlas builder reads them."""
    return [f"{target_id}_{corner}" for corner in range(4)]


def marker_detector(markers: MarkerSet) -> cv.aruco.ArucoDetector:
    """A detector of the set's dictionary, its corners refined to sub-pixel."""
    parameters = cv.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv.aruco.CORNER_REFINE_SUBPIX
    return cv.aruco.ArucoDetector(
        cv.aruco.getPredefinedDictionary(markers.dictionary_id), parameters
    )


def detect(
    detector: cv.aruco.ArucoDetector,
    markers: MarkerSet,
    frame: np.ndarray,
    moving: Iterable[int] = (),
) -> Detection:
    """The set's markers in a frame; those in moving are left out when the target's tag is in sight."""
    gray = frame if frame.ndim == 2 else cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    found: dict[int, np.ndarray] = {}
    if ids is not None:
        for number, quad in zip(ids.ravel().tolist(), corners, strict=True):
            marker_id = int(number)
            # A marker seen twice is a reflection or a second print: neither can be trusted.
            found[marker_id] = quad.reshape(4, 2) if marker_id not in found else np.empty((0, 2))
    tag_quad = found.get(markers.target_id)
    tag = None
    if tag_quad is not None and len(tag_quad) == 4:
        tag = _quad(tag_quad)
    skipped = set(moving) if tag is not None else set()
    landmarks = {
        landmark_id(marker_id, corner): (float(x), float(y))
        for marker_id, quad in sorted(found.items())
        if marker_id in markers.landmark_ids and marker_id not in skipped and len(quad) == 4
        for corner, (x, y) in enumerate(quad)
    }
    return Detection(landmarks=landmarks, tag=tag)


def tag_centre(tag: tuple[Vec2, Vec2, Vec2, Vec2]) -> Vec2:
    """Where the centre of a square lands in the image: the crossing of its diagonals.

    Under perspective the mean of the four corners is not the projected centre;
    the crossing of the diagonals is, since lines stay lines.
    """
    a, b, c, d = (np.array([x, y, 1.0]) for x, y in tag)
    centre = np.cross(np.cross(a, c), np.cross(b, d))
    return float(centre[0] / centre[2]), float(centre[1] / centre[2])


def clicks_of(detection: Detection, target_id: str) -> dict[str, Vec2]:
    """A frame's detection as the clicks of an annotator: landmark corners, the target's point and tag corners."""
    marked = dict(detection.landmarks)
    if detection.tag is not None:
        marked[target_id] = tag_centre(detection.tag)
        marked.update(zip(tag_point_ids(target_id), detection.tag, strict=True))
    return marked


def _quad(quad: np.ndarray) -> tuple[Vec2, Vec2, Vec2, Vec2]:
    a, b, c, d = ((float(x), float(y)) for x, y in quad)
    return a, b, c, d
