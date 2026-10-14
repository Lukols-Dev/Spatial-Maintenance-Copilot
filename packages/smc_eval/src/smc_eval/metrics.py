"""The measures the evaluation reports, as plain functions of numbers and poses."""

import math
from collections.abc import Sequence

import cv2 as cv
import numpy as np
from smc_core.calibration import Intrinsics
from smc_core.contracts import Contract, Pose, UncertaintyRegion, Vec2, Vec3
from smc_core.viewpoints import camera_centre

# z of the standard normal for a two-sided 95% interval.
Z_95 = 1.959963984540054


class Rate(Contract):
    """k of n, with the Wilson 95% interval: honest at the small n of one recorded asset."""

    k: int
    n: int
    rate: float | None
    low: float | None
    high: float | None


class Spread(Contract):
    n: int
    mean: float | None
    median: float | None
    p90: float | None
    max: float | None


def rate(k: int, n: int) -> Rate:
    if n == 0:
        return Rate(k=0, n=0, rate=None, low=None, high=None)
    low, high = wilson(k, n)
    return Rate(k=k, n=n, rate=k / n, low=low, high=high)


def wilson(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval of k successes in n trials."""
    if not 0 <= k <= n or n == 0:
        raise ValueError(f"no interval for {k} of {n}")
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def spread(values: Sequence[float]) -> Spread:
    if not values:
        return Spread(n=0, mean=None, median=None, p90=None, max=None)
    array = np.asarray(values, np.float64)
    return Spread(
        n=len(values),
        mean=float(array.mean()),
        median=float(np.median(array)),
        p90=float(np.percentile(array, 90)),
        max=float(array.max()),
    )


def chi2_2dof(confidence: float) -> float:
    """The squared Mahalanobis radius holding `confidence` of a 2D Gaussian."""
    return -2.0 * math.log(1.0 - confidence)


def mahalanobis2(region: UncertaintyRegion, centre: Vec2, point: Vec2) -> float | None:
    """The squared Mahalanobis distance of point from centre under the region's covariance.

    The test in_region holds against chi2_2dof(0.95); here the number itself,
    so coverage can be read at any confidence. None when the covariance cannot
    be inverted.
    """
    offset = np.array(point, np.float64) - np.array(centre, np.float64)
    try:
        return float(offset @ np.linalg.solve(np.array(region.covariance_px), offset))
    except np.linalg.LinAlgError:
        return None


def distance(a: Vec2, b: Vec2) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def pose_gap(a: Pose, b: Pose) -> tuple[float, float]:
    """How far apart two camera poses are: camera centres in mm, rotation in degrees."""
    translation = float(np.linalg.norm(camera_centre(a) - camera_centre(b)))
    rotation_a, _ = cv.Rodrigues(np.array(a.rvec, np.float64))
    rotation_b, _ = cv.Rodrigues(np.array(b.rvec, np.float64))
    relative, _ = cv.Rodrigues(rotation_a @ rotation_b.T)
    return translation, math.degrees(float(np.linalg.norm(relative)))


def project(point_mm: Vec3, pose: Pose, intrinsics: Intrinsics) -> Vec2:
    """Where a point of the asset frame lands in the image of a camera at pose."""
    projected, _ = cv.projectPoints(
        np.array([point_mm], np.float64),
        np.array(pose.rvec, np.float64),
        np.array(pose.tvec_mm, np.float64),
        intrinsics["camera_matrix"],
        intrinsics["dist_coeffs"],
    )
    return float(projected[0, 0, 0]), float(projected[0, 0, 1])
