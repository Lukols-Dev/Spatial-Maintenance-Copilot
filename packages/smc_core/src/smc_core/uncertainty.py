import cv2 as cv
import numpy as np

from smc_core.calibration import Intrinsics
from smc_core.contracts import Ellipse, Target, UncertaintyRegion, Vec2
from smc_core.pose import Correspondences, PoseFit

# Squared Mahalanobis radius that holds 95% of a 2D Gaussian: the chi-square
# quantile for two degrees of freedom.
CHI2_95_2DOF = 5.991464547107979


def target_region(
    pairs: Correspondences,
    fit: PoseFit,
    target: Target,
    intrinsics: Intrinsics,
    samples: int = 500,
    seed: int = 0,
) -> UncertaintyRegion | None:
    """Monte Carlo spread of the projected target centre.

    Each sample moves every inlier observation by its sigma_px, every inlier
    landmark by its sigma_mm and the target by its sigma_mm, fits the pose
    again starting from the estimate and projects the target. The 95% ellipse
    of those projections is the uncertainty region.

    pose_only projects the target from its atlas position, so it keeps only the
    spread that comes from the pose: the part a better view of the landmarks
    can shrink. The rest comes from the atlas and no viewpoint changes it.

    The intrinsics stay fixed. The calibration reports a standard deviation per
    parameter but not their correlation, and k1, k2 and k3 are strongly
    correlated, so sampling them independently would overstate the spread.

    Returns None when fewer than two samples give a pose with the target in
    front of the camera, because no covariance can be estimated from that.
    """
    camera_matrix, dist_coeffs = intrinsics["camera_matrix"], intrinsics["dist_coeffs"]
    inliers = fit["inliers"]
    object_points = pairs["object_points"][inliers]
    image_points = pairs["image_points"][inliers]
    sigma_mm = pairs["sigma_mm"][inliers][:, None]
    sigma_px = pairs["sigma_px"][inliers][:, None]
    centre = np.array(target.position_mm, np.float64)

    rng = np.random.default_rng(seed)
    total: list[np.ndarray] = []
    pose_only: list[np.ndarray] = []
    for _ in range(samples):
        # Draw every number before anything can be skipped, so a sample that
        # fails does not shift the random stream of the ones after it.
        moved_points = object_points + rng.standard_normal(object_points.shape) * sigma_mm
        moved_pixels = image_points + rng.standard_normal(image_points.shape) * sigma_px
        moved_centre = centre + rng.standard_normal(3) * target.sigma_mm

        found, rvec, tvec = cv.solvePnP(
            moved_points,
            moved_pixels,
            camera_matrix,
            dist_coeffs,
            fit["rvec"].copy(),
            fit["tvec"].copy(),
            useExtrinsicGuess=True,
            flags=cv.SOLVEPNP_ITERATIVE,
        )
        if not found:
            continue

        both = np.array([moved_centre, centre])
        rotation, _ = cv.Rodrigues(rvec)
        if ((both @ rotation.T + tvec.ravel())[:, 2] <= 0).any():
            continue

        projected, _ = cv.projectPoints(both, rvec, tvec, camera_matrix, dist_coeffs)
        total.append(projected[0, 0])
        pose_only.append(projected[1, 0])

    if len(total) < 2:
        return None

    covariance = np.cov(np.array(total).T)
    return UncertaintyRegion(
        confidence=0.95,
        covariance_px=(
            (float(covariance[0, 0]), float(covariance[0, 1])),
            (float(covariance[1, 0]), float(covariance[1, 1])),
        ),
        ellipse=ellipse_95(covariance),
        pose_only=ellipse_95(np.cov(np.array(pose_only).T)),
        samples=samples,
        failed_samples=samples - len(total),
        seed=seed,
    )


def in_region(region: UncertaintyRegion, centre: Vec2, point: Vec2) -> bool | None:
    """Whether point lies inside the 95% region around centre, the projected target.

    The test is the region's own: the squared Mahalanobis distance under its
    covariance against CHI2_95_2DOF, the boundary of the drawn ellipse. None
    when the covariance has no spread in some direction and cannot be inverted.
    """
    offset = np.array(point, np.float64) - np.array(centre, np.float64)
    try:
        distance = float(offset @ np.linalg.solve(np.array(region.covariance_px), offset))
    except np.linalg.LinAlgError:
        return None
    return distance <= CHI2_95_2DOF


def ellipse_95(covariance: np.ndarray) -> Ellipse:
    """The ellipse holding 95% of a 2D Gaussian with this covariance."""
    values, vectors = np.linalg.eigh(covariance)  # ascending eigenvalues
    major = vectors[:, 1]
    return Ellipse(
        semi_major_px=float(np.sqrt(CHI2_95_2DOF * values[1])),
        semi_minor_px=float(np.sqrt(CHI2_95_2DOF * max(values[0], 0.0))),
        angle_deg=float(np.degrees(np.arctan2(major[1], major[0])) % 180.0),
    )
