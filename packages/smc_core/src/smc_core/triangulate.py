from itertools import combinations
from typing import TypedDict

import cv2 as cv
import numpy as np

from smc_core.board_pose import ViewPose
from smc_core.calibration import Intrinsics
from smc_core.contracts import Vec2

GAUSS_NEWTON_STEPS = 5
MIN_VALID_SAMPLES = 10


class PointEstimate(TypedDict):
    """A point located from several views, with its spread."""

    position_mm: np.ndarray  # (3,) in the board frame
    sigma_mm: float  # 1-sigma of each coordinate, from the Monte Carlo spread
    residuals_px: np.ndarray  # (V,) reprojection error in each view, input order
    ray_angle_deg: float  # widest angle between two views' lines of sight
    failed_samples: int


def _triangulate(
    rotations: np.ndarray, tvecs: np.ndarray, normalised: np.ndarray
) -> np.ndarray | None:
    """The point whose projections best match these normalised image positions.

    rotations (V, 3, 3) and tvecs (V, 3) are the camera poses, normalised (V, 2)
    the observations after removing the lens. A linear solve gives the start and
    Gauss-Newton minimises the reprojection error. Returns None when the point
    ends up behind any camera.
    """
    rows = rotations.shape[0]
    a = np.empty((2 * rows, 3))
    b = np.empty(2 * rows)
    for i in range(rows):
        x, y = normalised[i]
        r, t = rotations[i], tvecs[i]
        a[2 * i], b[2 * i] = x * r[2] - r[0], t[0] - x * t[2]
        a[2 * i + 1], b[2 * i + 1] = y * r[2] - r[1], t[1] - y * t[2]
    point = np.linalg.lstsq(a, b, rcond=None)[0]

    for _ in range(GAUSS_NEWTON_STEPS):
        camera = np.einsum("vij,j->vi", rotations, point) + tvecs
        depth = camera[:, 2]
        if (depth <= 0).any():
            return None
        residual = normalised - camera[:, :2] / depth[:, None]
        scale = (depth**2)[:, None]
        jx = (rotations[:, 0, :] * depth[:, None] - camera[:, 0:1] * rotations[:, 2, :]) / scale
        jy = (rotations[:, 1, :] * depth[:, None] - camera[:, 1:2] * rotations[:, 2, :]) / scale
        jacobian = np.stack([jx, jy], axis=1).reshape(-1, 3)
        point = point + np.linalg.lstsq(jacobian, residual.reshape(-1), rcond=None)[0]

    camera = np.einsum("vij,j->vi", rotations, point) + tvecs
    return None if (camera[:, 2] <= 0).any() else point


def _remove_lens(pixels: np.ndarray, intrinsics: Intrinsics) -> np.ndarray:
    """Pixel positions to normalised coordinates, for any array of (..., 2)."""
    flat = pixels.reshape(-1, 1, 2).astype(np.float64)
    normalised = cv.undistortPoints(flat, intrinsics["camera_matrix"], intrinsics["dist_coeffs"])
    return normalised.reshape(pixels.shape)


def locate_point(
    observations: list[tuple[ViewPose, Vec2]],
    intrinsics: Intrinsics,
    click_sigma_px: float,
    rng: np.random.Generator,
) -> PointEstimate | None:
    """Triangulate one point seen in two or more posed views.

    Monte Carlo: every sample refits the point with each view's pose replaced by
    one of its samples and each click moved by click_sigma_px, so the spread
    holds both the click error and the error of the board pose. The number of
    samples is the one the poses were built with.

    Returns None with fewer than two views, when the point falls behind a
    camera, or when too few samples succeed to estimate a spread.
    """
    if len(observations) < 2:
        return None

    poses = [pose for pose, _ in observations]
    pixels = np.array([pixel for _, pixel in observations], np.float64)
    count = poses[0]["rotation_samples"].shape[0]
    rotation_samples = np.stack([p["rotation_samples"] for p in poses], axis=1)
    tvec_samples = np.stack([p["tvec_samples"] for p in poses], axis=1)

    moved = pixels[None] + rng.standard_normal((count, *pixels.shape)) * click_sigma_px
    normalised = _remove_lens(np.concatenate([pixels[None], moved]), intrinsics)

    rotations = np.stack([p["rotation"] for p in poses])
    tvecs = np.stack([p["tvec"] for p in poses])
    position = _triangulate(rotations, tvecs, normalised[0])
    if position is None:
        return None

    points = []
    for index in range(count):
        sample = _triangulate(rotation_samples[index], tvec_samples[index], normalised[index + 1])
        if sample is not None:
            points.append(sample)
    if len(points) < MIN_VALID_SAMPLES:
        return None
    covariance = np.cov(np.array(points).T)

    residuals = []
    for pose, pixel in observations:
        rvec, _ = cv.Rodrigues(pose["rotation"])
        projected, _ = cv.projectPoints(
            position[None],
            rvec,
            pose["tvec"],
            intrinsics["camera_matrix"],
            intrinsics["dist_coeffs"],
        )
        residuals.append(float(np.linalg.norm(projected.reshape(2) - np.array(pixel))))

    centres = [-pose["rotation"].T @ pose["tvec"] for pose in poses]
    rays = [(position - c) / np.linalg.norm(position - c) for c in centres]
    widest = max(np.degrees(np.arccos(np.clip(a @ b, -1.0, 1.0))) for a, b in combinations(rays, 2))

    return {
        "position_mm": position,
        "sigma_mm": float(np.sqrt(np.trace(covariance) / 3)),
        "residuals_px": np.array(residuals),
        "ray_angle_deg": float(widest),
        "failed_samples": count - len(points),
    }
