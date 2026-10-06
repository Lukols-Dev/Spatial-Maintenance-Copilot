import numpy as np

from smc_core.calibration import Intrinsics
from smc_core.contracts import Atlas, Failure, Localisation, Pose, View
from smc_core.pose import (
    MIN_CORRESPONDENCES,
    correspondences,
    fit_pose,
    measure_quality,
    project_target,
)
from smc_core.uncertainty import target_region


def localise(
    atlas: Atlas, view: View, intrinsics: Intrinsics, samples: int = 500, seed: int = 0
) -> Localisation:
    """Pose, target projection, quality and uncertainty region for one view.

    A view taken in another capture mode than the intrinsics, or one that
    names a landmark the atlas does not know, is a wiring error and raises.
    Whatever can go wrong with the observations themselves comes back as a
    Failure, with every field computed up to that point.

    samples and seed drive the Monte Carlo region; the same seed gives the
    same region.
    """
    if view.camera_id != intrinsics["camera_id"]:
        raise ValueError(
            f"{view.view_id} was taken as {view.camera_id}, "
            f"but the intrinsics are for {intrinsics['camera_id']}"
        )

    pairs = correspondences(atlas, view)
    if len(pairs["ids"]) < MIN_CORRESPONDENCES:
        return Localisation(view_id=view.view_id, failure=Failure.TOO_FEW_CORRESPONDENCES)

    # Landmarks on one line leave the rotation about that line undetermined.
    centred = pairs["object_points"] - pairs["object_points"].mean(axis=0)
    if np.linalg.matrix_rank(centred) < 2:
        return Localisation(view_id=view.view_id, failure=Failure.DEGENERATE_GEOMETRY)

    fit = fit_pose(pairs, intrinsics)
    if fit is None:
        return Localisation(view_id=view.view_id, failure=Failure.PNP_FAILED)

    quality = measure_quality(pairs, fit, intrinsics)
    rvec, tvec = fit["rvec"], fit["tvec"]
    pose = Pose(
        rvec=(float(rvec[0]), float(rvec[1]), float(rvec[2])),
        tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
    )

    target = project_target(atlas.target, fit, intrinsics)
    if target is None:
        return Localisation(
            view_id=view.view_id, failure=Failure.TARGET_BEHIND_CAMERA, quality=quality, pose=pose
        )

    region = target_region(pairs, fit, atlas.target, intrinsics, samples, seed)
    if region is None:
        return Localisation(
            view_id=view.view_id,
            failure=Failure.UNSTABLE_POSE,
            quality=quality,
            pose=pose,
            target=target,
        )

    return Localisation(
        view_id=view.view_id, quality=quality, pose=pose, target=target, uncertainty=region
    )
