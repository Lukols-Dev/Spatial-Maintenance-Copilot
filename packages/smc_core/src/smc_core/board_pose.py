from collections.abc import Iterable
from typing import TypedDict

import cv2 as cv
import numpy as np

from smc_core.calibration import Intrinsics, check_frame_size, collect_correspondences


class ViewPose(TypedDict):
    """Where the camera stood in one frame, measured from the printed board.

    rotation and tvec map board coordinates to camera coordinates:
    x_camera = rotation @ x_board + tvec, in millimetres.

    The samples are the same pose refitted after moving every detected corner
    by its sigma. They carry the pose error into whatever is triangulated from
    this view, and the error is the same for every point seen in the view.
    """

    rotation: np.ndarray  # (3, 3)
    tvec: np.ndarray  # (3,)
    rotation_samples: np.ndarray  # (S, 3, 3)
    tvec_samples: np.ndarray  # (S, 3)
    corners: int
    rms_px: float


def board_view_pose(
    detector: cv.aruco.CharucoDetector,
    board: cv.aruco.CharucoBoard,
    frame: np.ndarray,
    intrinsics: Intrinsics,
    rng: np.random.Generator,
    corner_sigma_px: float | None = None,
    samples: int = 200,
    min_corners: int = 8,
) -> ViewPose | None:
    """Camera pose in the board frame, or None when the board is not found.

    corner_sigma_px is how far a detected corner may be from the truth. When
    omitted it is the RMS reprojection error of the calibration, the one
    measured figure for how well corners sit in this camera's images.

    The board is flat, so a view that is nearly frontal can have its pose
    flip to the mirrored solution. Take board views at an angle.
    """
    check_frame_size(intrinsics, frame)
    sigma = intrinsics["rms"] if corner_sigma_px is None else corner_sigma_px

    object_points, image_points, used, _ = collect_correspondences(
        detector, board, [("frame", frame)], min_corners
    )
    if not used:
        return None
    obj = object_points[0].reshape(-1, 3).astype(np.float64)
    img = image_points[0].reshape(-1, 2).astype(np.float64)
    camera_matrix, dist_coeffs = intrinsics["camera_matrix"], intrinsics["dist_coeffs"]

    found, rvec, tvec = cv.solvePnP(obj, img, camera_matrix, dist_coeffs, flags=cv.SOLVEPNP_IPPE)
    if not found:
        return None
    rvec, tvec = cv.solvePnPRefineLM(obj, img, camera_matrix, dist_coeffs, rvec, tvec)

    projected, _ = cv.projectPoints(obj, rvec, tvec, camera_matrix, dist_coeffs)
    rms = float(np.sqrt(np.mean(np.sum((projected.reshape(-1, 2) - img) ** 2, axis=1))))

    rotation_samples = np.empty((samples, 3, 3))
    tvec_samples = np.empty((samples, 3))
    for index in range(samples):
        moved = img + rng.standard_normal(img.shape) * sigma
        refitted, r, t = cv.solvePnP(
            obj,
            moved,
            camera_matrix,
            dist_coeffs,
            rvec.copy(),
            tvec.copy(),
            useExtrinsicGuess=True,
            flags=cv.SOLVEPNP_ITERATIVE,
        )
        if not refitted:
            r, t = rvec, tvec
        rotation_samples[index], _ = cv.Rodrigues(r)
        tvec_samples[index] = t.ravel()

    rotation, _ = cv.Rodrigues(rvec)
    return {
        "rotation": rotation,
        "tvec": tvec.ravel(),
        "rotation_samples": rotation_samples,
        "tvec_samples": tvec_samples,
        "corners": len(obj),
        "rms_px": rms,
    }


def pose_views(
    frames: Iterable[tuple[str, np.ndarray]],
    detector: cv.aruco.CharucoDetector,
    board: cv.aruco.CharucoBoard,
    intrinsics: Intrinsics,
    rng: np.random.Generator,
    samples: int = 200,
) -> dict[str, ViewPose]:
    """Pose every frame in which the board is found, keyed by the frame's name.

    The frames draw their pose samples from one generator, in the order they
    come, so a pose depends on the frames before it. The atlas CLI and the
    service both pose through here: the same frames and seed give the same
    atlas either way.
    """
    poses: dict[str, ViewPose] = {}
    for name, frame in frames:
        pose = board_view_pose(detector, board, frame, intrinsics, rng, samples=samples)
        if pose is not None:
            poses[name] = pose
    return poses
