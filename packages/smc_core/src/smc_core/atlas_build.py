from typing import TypedDict

import numpy as np

from smc_core.board_pose import ViewPose
from smc_core.calibration import Intrinsics
from smc_core.contracts import Atlas, Clicks, Landmark, Target, Vec3
from smc_core.triangulate import PointEstimate, locate_point


class AtlasReport(TypedDict):
    """What went into an atlas, for reading before trusting it."""

    points: dict[str, PointEstimate]  # every point that was located, target included
    views_per_point: dict[str, int]  # posed views each located point was seen in
    skipped: dict[str, str]  # point id -> why it is not in the atlas
    unposed_views: list[str]  # views with clicks in which the board was not found


def build_atlas(
    poses: dict[str, ViewPose],
    clicks: Clicks,
    intrinsics: Intrinsics,
    *,
    asset_id: str,
    version: str,
    frame: str,
    target_id: str,
    target_extent_mm: Vec3,
    click_sigma_px: float,
    target_centre_sigma_mm: float,
    seed: int = 0,
) -> tuple[Atlas, AtlasReport]:
    """Triangulate every clicked point in the board frame and assemble the atlas.

    poses: view name -> pose, for the views in which the board was found. Views
    without a pose cannot be used and are listed in the report.

    Every point except target_id becomes a landmark. A point needs clicks in at
    least two posed views. The target is a box, not a point, so the position of
    its centre is uncertain by more than the clicks say: target_centre_sigma_mm
    is added in quadrature.

    Raises ValueError when the target cannot be located, since an atlas
    without a target has no use.
    """
    if clicks.camera_id != intrinsics["camera_id"]:
        raise ValueError(
            f"clicks were made on {clicks.camera_id} frames, "
            f"but the intrinsics are for {intrinsics['camera_id']}"
        )

    unposed = sorted(name for name in clicks.views if name not in poses)
    observations: dict[str, list[tuple[ViewPose, tuple[float, float]]]] = {}
    for name in sorted(clicks.views):
        if name not in poses:
            continue
        for point_id, pixel in clicks.views[name].items():
            observations.setdefault(point_id, []).append((poses[name], pixel))

    rng = np.random.default_rng(seed)
    points: dict[str, PointEstimate] = {}
    skipped: dict[str, str] = {}
    for point_id in sorted(observations):
        seen = observations[point_id]
        if len(seen) < 2:
            skipped[point_id] = f"seen in {len(seen)} posed view, needs 2"
            continue
        estimate = locate_point(seen, intrinsics, click_sigma_px, rng)
        if estimate is None:
            skipped[point_id] = "could not be triangulated: behind a camera or too unstable"
            continue
        points[point_id] = estimate

    if target_id not in points:
        reason = skipped.get(target_id, "never clicked")
        raise ValueError(f"target {target_id!r} is not located: {reason}")

    def vec(position: np.ndarray) -> Vec3:
        return (float(position[0]), float(position[1]), float(position[2]))

    centre = points[target_id]
    atlas = Atlas(
        asset_id=asset_id,
        version=version,
        frame=frame,
        landmarks=[
            Landmark(
                id=point_id,
                position_mm=vec(estimate["position_mm"]),
                sigma_mm=estimate["sigma_mm"],
            )
            for point_id, estimate in points.items()
            if point_id != target_id
        ],
        target=Target(
            id=target_id,
            position_mm=vec(centre["position_mm"]),
            sigma_mm=float(np.hypot(centre["sigma_mm"], target_centre_sigma_mm)),
            extent_mm=target_extent_mm,
        ),
    )
    report: AtlasReport = {
        "points": points,
        "views_per_point": {pid: len(observations[pid]) for pid in points},
        "skipped": skipped,
        "unposed_views": unposed,
    }
    return atlas, report
