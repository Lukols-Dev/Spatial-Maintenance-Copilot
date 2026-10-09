from typing import TypedDict, cast

import cv2 as cv
import numpy as np

from smc_core.calibration import Intrinsics
from smc_core.contracts import Atlas, Pose, ProjectedTarget, Quality, Target, Vec2, View

# PnP has a unique solution from four points in general position. Three points
# can have up to four.
MIN_CORRESPONDENCES = 4


class Correspondences(TypedDict):
    """The landmarks seen in one view, paired with their atlas positions.

    All arrays have one row per observation, in the order of the view.
    """

    ids: list[str]
    object_points: np.ndarray  # (N, 3) mm, asset frame
    image_points: np.ndarray  # (N, 2) px
    sigma_px: np.ndarray  # (N,)
    sigma_mm: np.ndarray  # (N,)


class PoseFit(TypedDict):
    """A pose and the correspondences it agrees with."""

    rvec: np.ndarray  # (3,) Rodrigues rotation, asset frame to camera frame
    tvec: np.ndarray  # (3,) mm
    inliers: np.ndarray  # (N,) bool, one per correspondence


def correspondences(atlas: Atlas, view: View) -> Correspondences:
    """Pair every observation in the view with its landmark in the atlas.

    An observation of a landmark the atlas does not know is a labelling error,
    not a weak observation, so it raises instead of being skipped.
    """
    landmarks = {landmark.id: landmark for landmark in atlas.landmarks}
    unknown = [o.landmark_id for o in view.observations if o.landmark_id not in landmarks]
    if unknown:
        raise ValueError(f"{view.view_id}: landmarks not in atlas {atlas.asset_id}: {unknown}")

    seen = [landmarks[o.landmark_id] for o in view.observations]
    return {
        "ids": [o.landmark_id for o in view.observations],
        "object_points": np.array([lm.position_mm for lm in seen], np.float64).reshape(-1, 3),
        "image_points": np.array([o.pixel for o in view.observations], np.float64).reshape(-1, 2),
        "sigma_px": np.array([o.sigma_px for o in view.observations], np.float64),
        "sigma_mm": np.array([lm.sigma_mm for lm in seen], np.float64),
    }


def fit_pose(
    pairs: Correspondences, intrinsics: Intrinsics, ransac_threshold_px: float = 8.0
) -> PoseFit | None:
    """RANSAC over the correspondences, then Levenberg-Marquardt on the inliers.

    ransac_threshold_px is the reprojection error up to which a landmark counts
    as an inlier; 8 px is OpenCV's default. Returns None when no pose agrees
    with at least MIN_CORRESPONDENCES landmarks.

    Clicks that coincide are a fault of the annotation, not of the code, and
    OpenCV fails on them in its own ways: with four, RANSAC returns a pose of
    NaN; with more, SQPnP raises. Both come back as None, like any other view
    that no pose fits.
    """
    camera_matrix, dist_coeffs = intrinsics["camera_matrix"], intrinsics["dist_coeffs"]

    # The stubs declare the inlier array as always present, so without the cast
    # the None check below would be flagged as unreachable.
    try:
        found, rvec, tvec, inlier_index = cast(
            tuple[bool, np.ndarray, np.ndarray, np.ndarray | None],
            cv.solvePnPRansac(
                pairs["object_points"],
                pairs["image_points"],
                camera_matrix,
                dist_coeffs,
                reprojectionError=ransac_threshold_px,
                flags=cv.SOLVEPNP_SQPNP,
            ),
        )
    except cv.error:
        return None
    if not found or inlier_index is None or len(inlier_index) < MIN_CORRESPONDENCES:
        return None
    if not (np.isfinite(rvec).all() and np.isfinite(tvec).all()):
        return None

    inliers = np.zeros(len(pairs["ids"]), bool)
    inliers[inlier_index.ravel()] = True
    rvec, tvec = cv.solvePnPRefineLM(
        pairs["object_points"][inliers],
        pairs["image_points"][inliers],
        camera_matrix,
        dist_coeffs,
        rvec,
        tvec,
    )
    return {"rvec": rvec.ravel(), "tvec": tvec.ravel(), "inliers": inliers}


def measure_quality(pairs: Correspondences, fit: PoseFit, intrinsics: Intrinsics) -> Quality:
    """Reprojection errors and landmark spread of a fitted pose.

    These are measurements. Deciding which values are too poor to trust is the
    policy's job, so nothing here compares against a threshold.
    """
    projected, _ = cv.projectPoints(
        pairs["object_points"],
        fit["rvec"],
        fit["tvec"],
        intrinsics["camera_matrix"],
        intrinsics["dist_coeffs"],
    )
    errors = np.linalg.norm(projected.reshape(-1, 2) - pairs["image_points"], axis=1)
    inliers = fit["inliers"]
    inlier_errors = errors[inliers]

    width, height = intrinsics["image_size"]
    hull = cv.convexHull(pairs["image_points"][inliers].astype(np.float32))

    # Singular values of the centred inlier positions: how far the landmarks
    # extend along their three principal directions. A small last one means
    # they lie close to a plane, where a pose can flip between two solutions.
    inlier_points = pairs["object_points"][inliers]
    spread = np.linalg.svd(inlier_points - inlier_points.mean(axis=0), compute_uv=False)

    return Quality(
        observed=len(pairs["ids"]),
        inliers=int(inliers.sum()),
        inlier_ratio=float(inliers.mean()),
        outlier_ids=[i for i, inlier in zip(pairs["ids"], inliers, strict=True) if not inlier],
        rms_reprojection_px=float(np.sqrt(np.mean(inlier_errors**2))),
        max_reprojection_px=float(inlier_errors.max()),
        reprojection_px={i: float(e) for i, e in zip(pairs["ids"], errors, strict=True)},
        image_coverage=float(cv.contourArea(hull) / (width * height)),
        non_planarity=float(spread[2] / spread[0]) if spread[0] > 0 else 0.0,
    )


def project_target(target: Target, fit: PoseFit, intrinsics: Intrinsics) -> ProjectedTarget | None:
    """Put the target centre and the box of its extent into the frame.

    Returns None when any corner of the box is behind the camera: OpenCV still
    projects such points, to positions that mean nothing.
    """
    centre = np.array(target.position_mm, np.float64)
    signs = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], np.float64)
    points = np.vstack([centre, centre + signs * np.array(target.extent_mm) / 2])

    rotation, _ = cv.Rodrigues(fit["rvec"])
    depth = (points @ rotation.T + fit["tvec"])[:, 2]
    if (depth <= 0).any():
        return None

    projected, _ = cv.projectPoints(
        points, fit["rvec"], fit["tvec"], intrinsics["camera_matrix"], intrinsics["dist_coeffs"]
    )
    projected = projected.reshape(-1, 2)
    outline = cv.convexHull(projected[1:].astype(np.float32)).reshape(-1, 2)

    centre_px = (float(projected[0, 0]), float(projected[0, 1]))
    return ProjectedTarget(
        centre_px=centre_px,
        depth_mm=float(depth[0]),
        in_frame=in_frame(centre_px, intrinsics["image_size"]),
        outline_px=[(float(x), float(y)) for x, y in outline],
        radius_px=float(np.sqrt(cv.contourArea(outline) / np.pi)),
    )


def in_frame(pixel: Vec2, image_size: tuple[int, int]) -> bool:
    """Whether a pixel lands on an image of image_size (width, height)."""
    width, height = image_size
    return 0 <= pixel[0] < width and 0 <= pixel[1] < height


def project_landmarks(atlas: Atlas, pose: Pose, intrinsics: Intrinsics) -> dict[str, Vec2 | None]:
    """Where a pose puts every landmark of the atlas, observed or not, in atlas order.

    A landmark behind the camera maps to None: OpenCV still projects it, to a
    position that means nothing.
    """
    if not atlas.landmarks:
        return {}
    points = np.array([landmark.position_mm for landmark in atlas.landmarks], np.float64)
    rvec, tvec = np.array(pose.rvec, np.float64), np.array(pose.tvec_mm, np.float64)

    rotation, _ = cv.Rodrigues(rvec)
    depth = (points @ rotation.T + tvec)[:, 2]
    projected, _ = cv.projectPoints(
        points, rvec, tvec, intrinsics["camera_matrix"], intrinsics["dist_coeffs"]
    )
    return {
        landmark.id: None if z <= 0 else (float(u), float(v))
        for landmark, z, (u, v) in zip(
            atlas.landmarks, depth, projected.reshape(-1, 2), strict=True
        )
    }
