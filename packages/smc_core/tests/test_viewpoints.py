"""Recorded viewpoints: the views of a set, and those that fit a move.

The views of a set are checked on the synthetic scene of smc_core.testing; the
moves on built cameras, where every step is known.
"""

import math

import cv2 as cv
import numpy as np
import pytest
from smc_core.contracts import Action, Clicks, Pose
from smc_core.testing import (
    INTRINSICS,
    TARGET_ID,
    VIEWPOINTS,
    camera_pose,
    clicks_for,
    scene_atlas,
)
from smc_core.viewpoints import (
    MAX_ANGLE_DEG,
    MIN_STEP_MM,
    camera_centre,
    fitting_viewpoints,
    hidden_target_views,
    observed_view,
    poses_from_clicks,
    step_in_camera,
    truth_view,
)

LOOKING_ALONG_Z = (0.0, 0.0, 0.0)


def camera(
    at: tuple[float, float, float], rvec: tuple[float, float, float] = LOOKING_ALONG_Z
) -> Pose:
    """A camera standing at `at` in the asset frame, turned by rvec."""
    rotation, _ = cv.Rodrigues(np.array(rvec))
    tvec = -rotation @ np.array(at)
    return Pose(rvec=rvec, tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])))


HERE = camera((0.0, 0.0, -1000.0))


def test_a_camera_centre_is_where_it_stands() -> None:
    np.testing.assert_allclose(
        camera_centre(camera((10.0, -20.0, -900.0), (0.1, 0.2, 0.3))), [10.0, -20.0, -900.0]
    )


def test_a_step_is_seen_from_the_current_camera() -> None:
    np.testing.assert_allclose(
        step_in_camera(HERE, camera((-300.0, 0.0, -1000.0))), [-300.0, 0.0, 0.0], atol=1e-9
    )


Point = tuple[float, float, float]


@pytest.mark.parametrize(
    ("there", "away", "action"),
    [
        ((-400.0, 0.0, -1000.0), (400.0, 0.0, -1000.0), Action.MOVE_LEFT),
        ((400.0, 0.0, -1000.0), (-400.0, 0.0, -1000.0), Action.MOVE_RIGHT),
        ((0.0, -400.0, -1000.0), (0.0, 400.0, -1000.0), Action.MOVE_UP),
        ((0.0, 400.0, -1000.0), (0.0, -400.0, -1000.0), Action.MOVE_DOWN),
        ((0.0, 0.0, -600.0), (0.0, 0.0, -1400.0), Action.MOVE_CLOSER),
        ((0.0, 0.0, -1400.0), (0.0, 0.0, -600.0), Action.MOVE_BACK),
    ],
)
def test_each_move_finds_the_viewpoint_that_way(there: Point, away: Point, action: Action) -> None:
    candidates = {"there": camera(there), "away": camera(away)}

    assert fitting_viewpoints(HERE, candidates, action) == ["there"]


def test_the_most_aligned_comes_first() -> None:
    candidates = {
        "left_and_closer": camera((-400.0, 0.0, -600.0)),  # 45 degrees off left
        "left": camera((-400.0, 0.0, -1000.0)),
        "left_and_up": camera((-400.0, -100.0, -1000.0)),
    }

    assert fitting_viewpoints(HERE, candidates, Action.MOVE_LEFT) == [
        "left",
        "left_and_up",
        "left_and_closer",
    ]


def test_a_step_beyond_the_angle_does_not_fit() -> None:
    inside = math.radians(MAX_ANGLE_DEG - 5)
    outside = math.radians(MAX_ANGLE_DEG + 5)
    candidates = {
        "inside": camera((-400 * math.cos(inside), 0.0, -1000 + 400 * math.sin(inside))),
        "outside": camera((-400 * math.cos(outside), 0.0, -1000 + 400 * math.sin(outside))),
    }

    assert fitting_viewpoints(HERE, candidates, Action.MOVE_LEFT) == ["inside"]


def test_a_second_take_from_the_same_spot_is_no_move() -> None:
    candidates = {
        "same_spot": camera((-(MIN_STEP_MM - 10), 0.0, -1000.0)),
        "far": camera((-400.0, 0.0, -1000.0)),
    }

    assert fitting_viewpoints(HERE, candidates, Action.MOVE_LEFT) == ["far"]


def test_the_move_is_the_current_camera_s_not_the_asset_s() -> None:
    """A camera rolled 90 degrees about its axis has the asset's -y on its right."""
    rolled = camera((0.0, 0.0, -1000.0), (0.0, 0.0, math.pi / 2))
    candidates = {"asset_minus_y": camera((0.0, -400.0, -1000.0))}

    assert fitting_viewpoints(rolled, candidates, Action.MOVE_RIGHT) == ["asset_minus_y"]
    assert fitting_viewpoints(rolled, candidates, Action.MOVE_UP) == []


def test_accept_has_no_direction() -> None:
    assert fitting_viewpoints(HERE, {"left": camera((-400.0, 0.0, -1000.0))}, Action.ACCEPT) == []


# ---- the views of a set --------------------------------------------------------------

ATLAS = scene_atlas()
LANDMARKS = [landmark.id for landmark in ATLAS.landmarks]


def recorded(views: dict[str, list[str]]) -> Clicks:
    """A set whose files click the points named, where view_0's camera sees them.

    A point the scene does not have is clicked in the corner.
    """
    every = clicks_for(0.0).views["view_0.png"]
    return Clicks(
        camera_id=clicks_for(0.0).camera_id,
        views={
            name: {point: every.get(point, (10.0, 10.0)) for point in points}
            for name, points in views.items()
        },
    )


def test_an_observed_view_lists_the_atlas_s_landmarks_in_atlas_order() -> None:
    clicks = recorded({"B1_close.png": [*reversed(LANDMARKS), TARGET_ID, "a_stray_point"]})

    view = observed_view("B1_close.png", clicks, ATLAS, sigma_px=2.5)

    assert [observation.landmark_id for observation in view.observations] == LANDMARKS
    assert {observation.sigma_px for observation in view.observations} == {2.5}
    assert view.view_id == "B1_close.png"
    assert view.camera_id == clicks.camera_id


def test_a_view_never_clicked_observes_nothing() -> None:
    assert observed_view("nowhere.png", recorded({}), ATLAS, sigma_px=1.0).observations == []


def test_the_viewpoints_are_the_views_with_the_target_hidden() -> None:
    clicks = recorded(
        {
            "B2_close.png": LANDMARKS[:3],
            "B1_open.png": [*LANDMARKS, TARGET_ID],
            "B1_close.png": LANDMARKS,
            "B3_close.png": ["a_stray_point"],
            "B4_close.png": [],
        }
    )

    assert hidden_target_views(clicks, ATLAS) == ["B1_close.png", "B2_close.png"]


def test_the_truth_is_the_same_spot_with_the_target_in_sight() -> None:
    clicks = recorded(
        {
            "B1_close.png": LANDMARKS,
            "B1_1_close.png": LANDMARKS,
            "B1_open.png": [*LANDMARKS, TARGET_ID],
            "B10_open.png": [*LANDMARKS, TARGET_ID],
            "B2_close.png": LANDMARKS,
        }
    )

    assert truth_view("B1_close.png", clicks, TARGET_ID) == "B1_open.png"
    assert truth_view("B1_1_close.png", clicks, TARGET_ID) == "B1_open.png"
    assert truth_view("B2_close.png", clicks, TARGET_ID) is None
    assert truth_view("B1_open.png", clicks, TARGET_ID) is None


def test_poses_from_clicks_stand_where_the_cameras_stood() -> None:
    clicks = clicks_for(0.0)

    poses = poses_from_clicks(sorted(clicks.views), clicks, ATLAS, INTRINSICS)

    assert sorted(poses) == sorted(clicks.views)
    for index, (rvec, distance) in enumerate(VIEWPOINTS):
        rotation, tvec = camera_pose(rvec, distance)
        np.testing.assert_allclose(
            camera_centre(poses[f"view_{index}.png"]), -rotation.T @ tvec, atol=0.5
        )


def test_a_view_with_too_few_landmarks_has_no_pose() -> None:
    clicks = recorded({"B1_close.png": LANDMARKS, "B2_close.png": LANDMARKS[:3]})

    assert list(poses_from_clicks(["B1_close.png", "B2_close.png"], clicks, ATLAS, INTRINSICS)) == [
        "B1_close.png"
    ]
