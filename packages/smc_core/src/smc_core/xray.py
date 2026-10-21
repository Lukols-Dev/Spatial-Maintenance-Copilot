"""What stands between the camera and the hidden target: the asset's panels, and the target's box.

The target is hidden behind a face of the asset, the cabinet's flap or a car's
bumper. The atlas lists those faces as panels. The panel that the line of
sight from the camera to the target crosses is the one to show the operator,
since the target is behind it. It is found by geometry, not by recognising
anything in the image. The target's extent box comes out as its 8 corners, so
it can be drawn as a box behind that panel.
"""

import itertools

import cv2 as cv
import numpy as np

from smc_core.calibration import Intrinsics
from smc_core.contracts import Panel, Pose, ProjectedPanel, Target, Vec2, Vec3

# The corners of a box around its centre, in units of half its extent.
BOX_SIGNS = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], np.float64)
# Its 12 edges: the corner pairs that differ along one axis only.
BOX_EDGES = [
    (a, b)
    for a, b in itertools.combinations(range(8), 2)
    if np.count_nonzero(BOX_SIGNS[a] != BOX_SIGNS[b]) == 1
]

# The faces of an axis-aligned box: the axis across it and the side, 0 for the smaller value.
FACES = {"x-": (0, 0), "x+": (0, 1), "y-": (1, 0), "y+": (1, 1), "z-": (2, 0), "z+": (2, 1)}
# Around a face: which bound each of the two other axes takes at each corner.
AROUND = ((0, 0), (1, 0), (1, 1), (0, 1))


def box_corners(
    centre: Vec3,
    extent: Vec3,
    rvec: Vec3 = (0.0, 0.0, 0.0),
    offset: Vec3 = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """The 8 corners, in BOX_SIGNS order, of a box of that extent turned by rvec, its centre offset from centre.

    offset and extent are along the box's own axes; with no rvec those are the frame's.
    """
    rotation, _ = cv.Rodrigues(np.array(rvec, np.float64))
    local = np.array(offset, np.float64) + BOX_SIGNS * np.array(extent, np.float64) / 2
    return np.array(centre, np.float64) + local @ rotation.T


def target_box(target: Target) -> np.ndarray:
    """The 8 corners of the target's box in the asset frame."""
    return box_corners(target.position_mm, target.extent_mm, target.rvec, target.box_offset_mm)


def box_panels(minimum: Vec3, maximum: Vec3, names: dict[str, str]) -> list[Panel]:
    """The named faces of the axis-aligned box between two opposite corners.

    names maps a face, "x-" (the face at the smaller x) to "z+", to its panel id;
    a face left out is not a panel.
    """
    unknown = sorted(set(names) - set(FACES))
    if unknown:
        raise ValueError(f"no such faces {unknown}: faces are {sorted(FACES)}")
    bounds = np.array([minimum, maximum], np.float64)
    if (bounds[1] <= bounds[0]).any():
        raise ValueError(f"{maximum} is not above {minimum} along every axis")
    panels = []
    for face, panel_id in names.items():
        axis, side = FACES[face]
        others = [other for other in range(3) if other != axis]
        corners = []
        for first, second in AROUND:
            corner = np.empty(3)
            corner[axis] = bounds[side, axis]
            corner[others[0]] = bounds[first, others[0]]
            corner[others[1]] = bounds[second, others[1]]
            corners.append((float(corner[0]), float(corner[1]), float(corner[2])))
        panels.append(Panel(id=panel_id, corners_mm=corners))
    return panels


def crossed_panel(eye: np.ndarray, point: np.ndarray, panels: list[Panel]) -> Panel | None:
    """The first panel the segment from eye to point passes through, or None."""
    nearest: tuple[float, Panel] | None = None
    ray = point - eye
    for panel in panels:
        corners = np.array(panel.corners_mm, np.float64)
        normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
        across = float(normal @ ray)
        if abs(across) < 1e-12:
            continue
        along = float(normal @ (corners[0] - eye)) / across
        if not 0.0 < along < 1.0:
            continue
        if _inside(eye + along * ray, corners, normal) and (nearest is None or along < nearest[0]):
            nearest = (along, panel)
    return None if nearest is None else nearest[1]


def _inside(point: np.ndarray, corners: np.ndarray, normal: np.ndarray) -> bool:
    """Whether a point of the panel's plane lies inside its outline, which must be convex."""
    signs = [
        float(np.cross(corners[(index + 1) % len(corners)] - corner, point - corner) @ normal)
        for index, corner in enumerate(corners)
    ]
    return all(sign >= 0 for sign in signs) or all(sign <= 0 for sign in signs)


def occluder(
    panels: list[Panel], point: Vec3, pose: Pose, intrinsics: Intrinsics
) -> ProjectedPanel | None:
    """The panel between the camera at pose and point, as the camera sees it.

    None when no panel is crossed, and when the panel reaches behind the
    camera, where its outline lands nowhere.
    """
    if not panels:
        return None
    rotation, _ = cv.Rodrigues(np.array(pose.rvec, np.float64))
    eye = -rotation.T @ np.array(pose.tvec_mm, np.float64)
    panel = crossed_panel(eye, np.array(point, np.float64), panels)
    if panel is None:
        return None
    outline = project_outline(panel.corners_mm, pose, intrinsics)
    return None if outline is None else ProjectedPanel(panel_id=panel.id, outline_px=outline)


def project_outline(
    corners_mm: list[Vec3] | np.ndarray, pose: Pose, intrinsics: Intrinsics
) -> list[Vec2] | None:
    """Where an outline lands in the frame; None when any corner is behind the camera."""
    points = np.asarray(corners_mm, np.float64).reshape(-1, 3)
    rvec, tvec = np.array(pose.rvec, np.float64), np.array(pose.tvec_mm, np.float64)
    rotation, _ = cv.Rodrigues(rvec)
    if ((points @ rotation.T + tvec)[:, 2] <= 0).any():
        return None
    projected, _ = cv.projectPoints(
        points, rvec, tvec, intrinsics["camera_matrix"], intrinsics["dist_coeffs"]
    )
    return [(float(x), float(y)) for x, y in projected.reshape(-1, 2)]
