"""Recorded viewpoints: which show the target hidden, which is the truth of which,
where each camera stood, and which lie in the direction of a move.

A set of recorded views is a Clicks file: the landmarks and the target clicked
in each image. The target is clicked only where it is in sight, so a view whose
clicks mark landmarks and not the target shows it hidden: a viewpoint. Its
truth is the image of the same spot with the target in sight, the files sharing
the name up to the first "_" (B1_close.png, B1_open.png).

A camera's centre in the asset frame is -R^T t. The step from the current
camera to another one, turned into the current camera's frame (x right, y
down, z forward), is the way the operator would carry the phone: MOVE_LEFT is
-x, MOVE_UP is -y, MOVE_CLOSER is +z. A viewpoint fits a move when its step
points within MAX_ANGLE_DEG of the move's direction and is at least
MIN_STEP_MM long: a second take from the same spot is no move at all.
"""

import math
from collections.abc import Iterable

import cv2 as cv
import numpy as np

from smc_core.calibration import Intrinsics
from smc_core.contracts import Action, Atlas, Clicks, LandmarkObservation, Pose, View
from smc_core.pose import MIN_CORRESPONDENCES, correspondences, fit_pose

DIRECTIONS: dict[Action, tuple[float, float, float]] = {
    Action.MOVE_LEFT: (-1.0, 0.0, 0.0),
    Action.MOVE_RIGHT: (1.0, 0.0, 0.0),
    Action.MOVE_UP: (0.0, -1.0, 0.0),
    Action.MOVE_DOWN: (0.0, 1.0, 0.0),
    Action.MOVE_CLOSER: (0.0, 0.0, 1.0),
    Action.MOVE_BACK: (0.0, 0.0, -1.0),
}
# These pick viewpoints to suggest and never make a result reliable, so they
# are fixed here rather than calibrated in the Policy.
MAX_ANGLE_DEG = 60.0
MIN_STEP_MM = 50.0


def _rotation(pose: Pose) -> np.ndarray:
    rotation, _ = cv.Rodrigues(np.array(pose.rvec, np.float64))
    return rotation


def camera_centre(pose: Pose) -> np.ndarray:
    """Where the camera stands, in the asset frame, in millimetres."""
    return -_rotation(pose).T @ np.array(pose.tvec_mm, np.float64)


def step_in_camera(current: Pose, other: Pose) -> np.ndarray:
    """The step from the current camera to the other one, in the current camera's frame."""
    step: np.ndarray = _rotation(current) @ (camera_centre(other) - camera_centre(current))
    return step


def fitting_viewpoints(current: Pose, candidates: dict[str, Pose], action: Action) -> list[str]:
    """The candidates whose step from current fits the move, the most aligned first.

    Ties keep the candidates' order. A move without a direction (ACCEPT) fits none.
    """
    direction = DIRECTIONS.get(action)
    if direction is None:
        return []
    least_cosine = math.cos(math.radians(MAX_ANGLE_DEG))
    scored: list[tuple[float, int, str]] = []
    for order, (name, pose) in enumerate(candidates.items()):
        step = step_in_camera(current, pose)
        length = float(np.linalg.norm(step))
        if length < MIN_STEP_MM:
            continue
        cosine = float(step @ np.array(direction)) / length
        if cosine >= least_cosine:
            scored.append((-cosine, order, name))
    return [name for _, _, name in sorted(scored)]


# ---- the views of a set --------------------------------------------------------------


def observed_view(name: str, clicks: Clicks, atlas: Atlas, sigma_px: float) -> View:
    """The landmarks of the atlas clicked in one image, as localise() takes them.

    They come in atlas order, not click order: RANSAC and the Monte Carlo draws
    follow the rows, and the same clicks should give the same result however
    they were made. Clicked points that are not landmarks, the target among
    them, are left out.
    """
    marked = clicks.views.get(name, {})
    return View(
        view_id=name,
        camera_id=clicks.camera_id,
        observations=[
            LandmarkObservation(
                landmark_id=landmark.id, pixel=marked[landmark.id], sigma_px=sigma_px
            )
            for landmark in atlas.landmarks
            if landmark.id in marked
        ],
    )


def hidden_target_views(clicks: Clicks, atlas: Atlas) -> list[str]:
    """The viewpoints of a set: landmarks of the atlas clicked, the target not, in name order."""
    landmarks = {landmark.id for landmark in atlas.landmarks}
    target = atlas.target.id
    return sorted(
        name
        for name, marked in clicks.views.items()
        if target not in marked and landmarks & marked.keys()
    )


def truth_view(view: str, clicks: Clicks, target_id: str) -> str | None:
    """The image of the same spot with the target clicked, if the set has one."""
    prefix = view.split("_", 1)[0]
    paired = sorted(
        name
        for name, marked in clicks.views.items()
        if name != view and name.split("_", 1)[0] == prefix and target_id in marked
    )
    return paired[0] if paired else None


def poses_from_clicks(
    views: Iterable[str], clicks: Clicks, atlas: Atlas, intrinsics: Intrinsics
) -> dict[str, Pose]:
    """Where each view's camera stood: PnP with RANSAC on its clicks, nothing more.

    No Monte Carlo region: placing viewpoints relative to each other needs only
    the pose. A view no pose fits is left out.
    """
    poses: dict[str, Pose] = {}
    for name in views:
        pairs = correspondences(atlas, observed_view(name, clicks, atlas, sigma_px=1.0))
        if len(pairs["ids"]) < MIN_CORRESPONDENCES:
            continue
        fit = fit_pose(pairs, intrinsics)
        if fit is None:
            continue
        rvec, tvec = fit["rvec"], fit["tvec"]
        poses[name] = Pose(
            rvec=(float(rvec[0]), float(rvec[1]), float(rvec[2])),
            tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
        )
    return poses
