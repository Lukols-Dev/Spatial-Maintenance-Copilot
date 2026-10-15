"""Guidance toward the guide view, on the synthetic scene's known cameras."""

import cv2 as cv
import numpy as np
import pytest
from smc_core.contracts import Clicks, Pose
from smc_core.guidance import asset_points, choose_guide_view, guidance
from smc_core.testing import (
    CAMERA_ID,
    INTRINSICS,
    POINTS_MM,
    TARGET_ID,
    VIEWPOINTS,
    camera_pose,
    marker_atlas,
    project,
    scene_atlas,
)


def pose_at(index: int) -> Pose:
    rotation, tvec = camera_pose(*VIEWPOINTS[index])
    rvec = np.ravel(cv.Rodrigues(rotation)[0])
    return Pose(
        rvec=(float(rvec[0]), float(rvec[1]), float(rvec[2])),
        tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
    )


LANDMARKS = [point for point in POINTS_MM if point != TARGET_ID]


def clicked(views: dict[str, list[str]]) -> Clicks:
    return Clicks(
        camera_id=CAMERA_ID,
        views={name: dict.fromkeys(points, (500.0, 900.0)) for name, points in views.items()},
    )


def test_the_guide_view_saw_the_most_landmarks() -> None:
    poses = {"a.png": pose_at(0), "b.png": pose_at(1)}
    clicks = clicked({"a.png": LANDMARKS[:4], "b.png": LANDMARKS})

    assert choose_guide_view(poses, clicks, scene_atlas(), INTRINSICS) == poses["b.png"]


def test_among_equals_the_guide_view_has_the_target_nearest_the_middle() -> None:
    poses = {f"view_{index}.png": pose_at(index) for index in range(len(VIEWPOINTS))}
    clicks = clicked({name: LANDMARKS for name in poses})
    centre = np.array(INTRINSICS["image_size"]) / 2

    def off_centre(index: int) -> float:
        rotation, tvec = camera_pose(*VIEWPOINTS[index])
        return float(np.linalg.norm(project(POINTS_MM[TARGET_ID], rotation, tvec)[0] - centre))

    best = min(range(len(VIEWPOINTS)), key=off_centre)
    assert choose_guide_view(poses, clicks, scene_atlas(), INTRINSICS) == poses[f"view_{best}.png"]


def test_a_pose_with_the_target_behind_the_camera_guides_nowhere() -> None:
    # The target at z = 420 lands at z = -580 in this camera: behind it.
    turned_away = Pose(rvec=(0.0, 0.0, 0.0), tvec_mm=(0.0, 0.0, -1000.0))

    assert (
        choose_guide_view(
            {"away.png": turned_away}, clicked({"away.png": LANDMARKS}), scene_atlas(), INTRINSICS
        )
        is None
    )


def test_on_the_guide_view_the_camera_is_aligned() -> None:
    atlas = marker_atlas()
    assert atlas.guide_view is not None

    found = guidance(atlas.guide_view, atlas, INTRINSICS)

    assert found is not None
    assert found.alignment_px == pytest.approx(0.0, abs=1e-9)
    assert found.progress == pytest.approx(1.0)
    assert len(found.outlines_px) == len(atlas.panels) == 1


def test_progress_falls_as_the_camera_leaves_the_guide_view() -> None:
    atlas = marker_atlas()
    assert atlas.guide_view is not None
    near = pose_at(0) if pose_at(0) != atlas.guide_view else pose_at(1)
    far = Pose(rvec=near.rvec, tvec_mm=(near.tvec_mm[0] + 300.0, near.tvec_mm[1], near.tvec_mm[2]))

    at_near = guidance(near, atlas, INTRINSICS)
    at_far = guidance(far, atlas, INTRINSICS)

    assert at_near is not None and at_far is not None
    assert at_near.progress is not None and at_far.progress is not None
    assert 0.0 <= at_far.progress < at_near.progress <= 1.0


def test_without_a_pose_or_a_guide_view_there_is_no_measure() -> None:
    atlas = marker_atlas()

    no_pose = guidance(None, atlas, INTRINSICS)

    assert no_pose is not None and no_pose.alignment_px is None and no_pose.progress is None
    assert guidance(pose_at(0), scene_atlas(), INTRINSICS) is None


def test_the_asset_is_its_panels_corners_else_its_landmarks() -> None:
    assert asset_points(marker_atlas()).shape == (4, 3)
    assert asset_points(scene_atlas()).shape == (len(LANDMARKS), 3)
