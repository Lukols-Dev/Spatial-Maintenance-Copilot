"""The measures, on numbers whose answers are known."""

import math

import cv2 as cv
import numpy as np
import pytest
from smc_core import testing
from smc_core.contracts import Ellipse, Pose, UncertaintyRegion
from smc_core.testing import INTRINSICS, POINTS_MM, TARGET_ID, VIEWPOINTS, camera_pose
from smc_core.uncertainty import CHI2_95_2DOF
from smc_eval.metrics import chi2_2dof, mahalanobis2, pose_gap, project, rate, spread, wilson


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [(0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (5, 10, 0.2366, 0.7634), (12, 12, 0.7575, 1.0)],
)
def test_the_wilson_interval_matches_the_tables(k: int, n: int, low: float, high: float) -> None:
    found = wilson(k, n)

    assert found == pytest.approx((low, high), abs=1e-4)


def test_a_rate_of_nothing_has_no_value() -> None:
    assert rate(0, 0).rate is None
    assert rate(3, 4).rate == 0.75


def test_no_interval_for_an_impossible_count() -> None:
    with pytest.raises(ValueError, match="no interval"):
        wilson(5, 4)


def test_a_spread_of_values() -> None:
    found = spread([1.0, 2.0, 3.0, 4.0, 10.0])

    assert (found.n, found.mean, found.median, found.max) == (5, 4.0, 3.0, 10.0)
    assert found.p90 == pytest.approx(7.6)
    assert spread([]).median is None


def test_the_chi2_radius_of_95_is_the_region_s() -> None:
    assert chi2_2dof(0.95) == pytest.approx(CHI2_95_2DOF)
    assert chi2_2dof(0.5) == pytest.approx(1.386294, abs=1e-6)


def region(covariance: tuple[tuple[float, float], tuple[float, float]]) -> UncertaintyRegion:
    ellipse = Ellipse(semi_major_px=1.0, semi_minor_px=1.0, angle_deg=0.0)
    return UncertaintyRegion(
        confidence=0.95,
        covariance_px=covariance,
        ellipse=ellipse,
        pose_only=ellipse,
        samples=10,
        failed_samples=0,
        seed=0,
    )


def test_the_mahalanobis_distance_scales_by_the_spread() -> None:
    assert mahalanobis2(region(((4.0, 0.0), (0.0, 1.0))), (10.0, 10.0), (14.0, 11.0)) == (
        pytest.approx(4.0 + 1.0)
    )


def test_a_region_without_spread_has_no_distance() -> None:
    assert mahalanobis2(region(((0.0, 0.0), (0.0, 0.0))), (0.0, 0.0), (1.0, 1.0)) is None


def pose_of(rotation: np.ndarray, tvec: np.ndarray) -> Pose:
    rvec, _ = cv.Rodrigues(rotation)
    return Pose(
        rvec=(float(rvec[0, 0]), float(rvec[1, 0]), float(rvec[2, 0])),
        tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
    )


def test_the_gap_between_poses_is_the_camera_s_step_and_turn() -> None:
    rotation, tvec = camera_pose(*VIEWPOINTS[0])
    turn, _ = cv.Rodrigues(np.array([0.0, math.radians(10.0), 0.0]))
    # Turned about its own centre, and stepped 100 mm along its x axis.
    turned = pose_of(turn @ rotation, turn @ tvec)
    stepped = pose_of(rotation, tvec - np.array([100.0, 0.0, 0.0]))

    assert pose_gap(pose_of(rotation, tvec), turned) == pytest.approx((0.0, 10.0), abs=1e-6)
    assert pose_gap(pose_of(rotation, tvec), stepped) == pytest.approx((100.0, 0.0), abs=1e-6)


def test_a_point_projects_as_the_scene_s_camera_sees_it() -> None:
    rotation, tvec = camera_pose(*VIEWPOINTS[3])

    x, y, z = POINTS_MM[TARGET_ID]
    found = project((float(x), float(y), float(z)), pose_of(rotation, tvec), INTRINSICS)

    np.testing.assert_allclose(found, testing.project(POINTS_MM[TARGET_ID], rotation, tvec)[0])
