"""Guidance toward the atlas's guide view: a pose the target is known to be well localised from.

The guide view is one of the poses recorded while the atlas was built, the one
that saw the most landmarks with the target nearest the middle of the frame.
Seen from it, the asset's panels have an outline in the frame. Drawn over the
live image, that outline is where the asset should come to sit, as an AR app
shows the outline of the object to line up with.

How far the camera still is from that pose is measured in the frame: the mean
distance between the asset's points as the current pose puts them and as the
guide view puts them. It is 0 on the guide view. Progress turns that distance
into a share, 1 on the guide view and 0 at PROGRESS_SCALE of the image's
diagonal or beyond. It shows how close the operator is; it never makes a
result reliable, which only the policy does.
"""

import cv2 as cv
import numpy as np

from smc_core.calibration import Intrinsics
from smc_core.contracts import Atlas, Clicks, Guidance, Pose, Vec2
from smc_core.xray import project_outline

# The alignment, as a share of the image's diagonal, at which progress reaches 0.
PROGRESS_SCALE = 0.5


def choose_guide_view(
    poses: dict[str, Pose], clicks: Clicks, atlas: Atlas, intrinsics: Intrinsics
) -> Pose | None:
    """The recorded pose that saw the most landmarks of the atlas, the target nearest the middle among equals.

    poses are the camera poses the rig board gave while the atlas was built;
    a pose that puts the target behind the camera or out of the frame is no
    guide. None when no pose qualifies.
    """
    landmarks = {landmark.id for landmark in atlas.landmarks}
    width, height = intrinsics["image_size"]
    best: tuple[int, float, str] | None = None
    for name, pose in poses.items():
        target = project_outline([atlas.target.position_mm], pose, intrinsics)
        if target is None:
            continue
        x, y = target[0]
        if not (0 <= x < width and 0 <= y < height):
            continue
        seen = len(landmarks & clicks.views.get(name, {}).keys())
        off_centre = float(np.hypot(x - width / 2, y - height / 2))
        score = (-seen, off_centre, name)
        if best is None or score < best:
            best = score
    return None if best is None else poses[best[2]]


def asset_points(atlas: Atlas) -> np.ndarray:
    """The points whose places in the frame tell how the asset sits: its panels' corners, else its landmarks."""
    corners = {tuple(corner) for panel in atlas.panels for corner in panel.corners_mm}
    if corners:
        return np.array(sorted(corners), np.float64)
    return np.array([landmark.position_mm for landmark in atlas.landmarks], np.float64)


def guidance(pose: Pose | None, atlas: Atlas, intrinsics: Intrinsics) -> Guidance | None:
    """Where the asset should sit in the frame, and how far this pose is from there; None without a guide view."""
    guide = atlas.guide_view
    if guide is None:
        return None
    outlines = [
        outline
        for panel in atlas.panels
        if (outline := project_outline(panel.corners_mm, guide, intrinsics)) is not None
    ]
    alignment = None if pose is None else _alignment(pose, guide, asset_points(atlas), intrinsics)
    progress = None
    if alignment is not None:
        width, height = intrinsics["image_size"]
        scale = PROGRESS_SCALE * float(np.hypot(width, height))
        progress = float(np.clip(1.0 - alignment / scale, 0.0, 1.0))
    return Guidance(outlines_px=outlines, alignment_px=alignment, progress=progress)


def _alignment(pose: Pose, guide: Pose, points: np.ndarray, intrinsics: Intrinsics) -> float | None:
    """The mean distance between the points as pose and as guide put them, over those in front of both."""
    here, there = _project(points, pose, intrinsics), _project(points, guide, intrinsics)
    both = [(a, b) for a, b in zip(here, there, strict=True) if a is not None and b is not None]
    if not both:
        return None
    return float(np.mean([np.hypot(a[0] - b[0], a[1] - b[1]) for a, b in both]))


def _project(points: np.ndarray, pose: Pose, intrinsics: Intrinsics) -> list[Vec2 | None]:
    rvec, tvec = np.array(pose.rvec, np.float64), np.array(pose.tvec_mm, np.float64)
    rotation, _ = cv.Rodrigues(rvec)
    depth = (points @ rotation.T + tvec)[:, 2]
    projected, _ = cv.projectPoints(
        points, rvec, tvec, intrinsics["camera_matrix"], intrinsics["dist_coeffs"]
    )
    return [
        (float(x), float(y)) if z > 0 else None
        for (x, y), z in zip(projected.reshape(-1, 2), depth, strict=True)
    ]
