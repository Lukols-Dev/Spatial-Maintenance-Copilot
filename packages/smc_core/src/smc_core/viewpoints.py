"""Which recorded viewpoints lie in the direction of a move.

A camera's centre in the asset frame is -R^T t. The step from the current
camera to another one, turned into the current camera's frame (x right, y
down, z forward), is the way the operator would carry the phone: MOVE_LEFT is
-x, MOVE_UP is -y, MOVE_CLOSER is +z. A viewpoint fits a move when its step
points within MAX_ANGLE_DEG of the move's direction and is at least
MIN_STEP_MM long: a second take from the same spot is no move at all.
"""

import math

import cv2 as cv
import numpy as np

from smc_core.contracts import Action, Pose

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
