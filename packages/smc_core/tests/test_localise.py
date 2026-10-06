import cv2 as cv
import numpy as np
import pytest
from smc_core.calibration import Intrinsics
from smc_core.contracts import (
    Atlas,
    Failure,
    Landmark,
    LandmarkObservation,
    Localisation,
    Target,
    View,
)
from smc_core.localise import localise
from smc_core.uncertainty import CHI2_95_2DOF

CAMERA_ID = "phone-1x-portrait"
INTRINSICS: Intrinsics = {
    "camera_id": CAMERA_ID,
    "image_size": (1080, 1920),
    "camera_matrix": np.array([[1675.0, 0.0, 531.6], [0.0, 1677.4, 956.2], [0.0, 0.0, 1.0]]),
    "dist_coeffs": np.array([0.14, -0.15, 0.0, 0.0, 0.0]),
    "rms": 0.5,
    "std_intrinsics": np.zeros(9),
}

# Ten landmarks spread along all three axes, like points on a bumper, a
# headlight and a wheel arch, with the target behind them. Asset frame, mm.
LANDMARKS_MM = np.array(
    [
        [-350, -150, 0],
        [350, -150, 20],
        [-300, 120, 60],
        [320, 140, 40],
        [0, -180, -80],
        [-120, 30, 150],
        [150, -40, 120],
        [60, 170, -40],
        [-220, -60, 90],
        [240, 60, -60],
    ],
    np.float64,
)
TARGET_MM = np.array([40.0, 60.0, 260.0])

# The true camera: 1.5 m from the asset, turned slightly.
TRUE_RVEC = np.array([0.15, -0.25, 0.05])
TRUE_TVEC = np.array([30.0, -20.0, 1500.0])


def make_atlas(
    landmark_sigma_mm: float = 0.0,
    target_sigma_mm: float = 0.0,
    landmarks_mm: np.ndarray = LANDMARKS_MM,
    target_mm: np.ndarray = TARGET_MM,
) -> Atlas:
    return Atlas(
        asset_id="test-car",
        version="1",
        frame="synthetic",
        landmarks=[
            Landmark(id=f"L{i}", position_mm=(x, y, z), sigma_mm=landmark_sigma_mm)
            for i, (x, y, z) in enumerate(landmarks_mm.tolist())
        ],
        target=Target(
            id="washer_pump",
            position_mm=(target_mm[0], target_mm[1], target_mm[2]),
            sigma_mm=target_sigma_mm,
            extent_mm=(80.0, 60.0, 120.0),
        ),
    )


def project(points_mm: np.ndarray) -> np.ndarray:
    """Pixels of asset-frame points, as the camera at the true pose sees them."""
    projected, _ = cv.projectPoints(
        np.asarray(points_mm, np.float64).reshape(-1, 3),
        TRUE_RVEC,
        TRUE_TVEC,
        INTRINSICS["camera_matrix"],
        INTRINSICS["dist_coeffs"],
    )
    return projected.reshape(-1, 2)


def make_view(pixels: np.ndarray, sigma_px: float = 1.0, seen: list[int] | None = None) -> View:
    """A view in which landmark L<i> appears at pixels[i], for every i in seen."""
    seen = list(range(len(pixels))) if seen is None else seen
    return View(
        view_id="view_1",
        camera_id=CAMERA_ID,
        observations=[
            LandmarkObservation(
                landmark_id=f"L{i}", pixel=(pixels[i][0], pixels[i][1]), sigma_px=sigma_px
            )
            for i in seen
        ],
    )


def test_localise_recovers_the_pose_from_exact_observations() -> None:
    result = localise(make_atlas(), make_view(project(LANDMARKS_MM)), INTRINSICS)

    assert result.failure is None
    assert result.pose is not None and result.target is not None and result.quality is not None
    np.testing.assert_allclose(result.pose.rvec, TRUE_RVEC, atol=1e-6)
    np.testing.assert_allclose(result.pose.tvec_mm, TRUE_TVEC, atol=1e-3)
    np.testing.assert_allclose(result.target.centre_px, project(TARGET_MM)[0], atol=1e-3)
    assert result.target.in_frame
    assert result.quality.inliers == 10
    assert result.quality.rms_reprojection_px < 1e-3


def test_localise_sets_a_mislabelled_landmark_aside() -> None:
    pixels = project(LANDMARKS_MM)
    pixels[3] += (80.0, -60.0)

    result = localise(make_atlas(), make_view(pixels), INTRINSICS)

    assert result.quality is not None and result.target is not None
    assert result.quality.outlier_ids == ["L3"]
    assert result.quality.inliers == 9
    assert result.quality.reprojection_px["L3"] == pytest.approx(100.0, abs=1.0)
    np.testing.assert_allclose(result.target.centre_px, project(TARGET_MM)[0], atol=1e-3)


def test_localise_needs_four_landmarks() -> None:
    view = make_view(project(LANDMARKS_MM), seen=[0, 1, 2])

    result = localise(make_atlas(), view, INTRINSICS)

    assert result.failure is Failure.TOO_FEW_CORRESPONDENCES
    assert result.pose is None


def test_localise_refuses_landmarks_on_one_line() -> None:
    on_a_line = np.array([[x, 0.0, 0.0] for x in (-200.0, -100.0, 0.0, 100.0, 200.0)])

    result = localise(make_atlas(landmarks_mm=on_a_line), make_view(project(on_a_line)), INTRINSICS)

    assert result.failure is Failure.DEGENERATE_GEOMETRY


def test_localise_reports_a_target_behind_the_camera() -> None:
    atlas = make_atlas(target_mm=np.array([0.0, 0.0, -2000.0]))

    result = localise(atlas, make_view(project(LANDMARKS_MM)), INTRINSICS)

    assert result.failure is Failure.TARGET_BEHIND_CAMERA
    assert result.pose is not None
    assert result.target is None


def test_localise_refuses_a_view_from_another_capture_mode() -> None:
    view = make_view(project(LANDMARKS_MM)).model_copy(update={"camera_id": "phone-0.5x"})

    with pytest.raises(ValueError, match=r"taken as phone-0\.5x"):
        localise(make_atlas(), view, INTRINSICS)


def test_localise_refuses_a_landmark_the_atlas_does_not_know() -> None:
    observation = LandmarkObservation(landmark_id="X9", pixel=(100.0, 200.0), sigma_px=1.0)
    view = View(view_id="view_1", camera_id=CAMERA_ID, observations=[observation])

    with pytest.raises(ValueError, match="X9"):
        localise(make_atlas(), view, INTRINSICS)


def test_localisation_survives_a_json_round_trip() -> None:
    result = localise(make_atlas(), make_view(project(LANDMARKS_MM)), INTRINSICS, samples=50)

    assert Localisation.model_validate_json(result.model_dump_json()) == result


def test_uncertainty_region_holds_the_true_target_95_percent_of_the_time() -> None:
    """A region is only useful if its confidence is honest.

    Every trial draws new atlas errors and new observation noise, localises,
    and checks whether the true target centre lies inside the 95% ellipse.
    """
    landmark_sigma_mm, target_sigma_mm, sigma_px = 3.0, 5.0, 2.0
    atlas = make_atlas(landmark_sigma_mm, target_sigma_mm)
    rng = np.random.default_rng(7)

    trials, inside = 100, 0
    for trial in range(trials):
        true_landmarks = LANDMARKS_MM + rng.normal(0, landmark_sigma_mm, LANDMARKS_MM.shape)
        true_target = TARGET_MM + rng.normal(0, target_sigma_mm, 3)
        pixels = project(true_landmarks) + rng.normal(0, sigma_px, (len(LANDMARKS_MM), 2))

        result = localise(atlas, make_view(pixels, sigma_px), INTRINSICS, samples=200, seed=trial)

        assert result.target is not None and result.uncertainty is not None
        offset = project(true_target)[0] - np.array(result.target.centre_px)
        covariance = np.array(result.uncertainty.covariance_px)
        inside += bool(offset @ np.linalg.solve(covariance, offset) <= CHI2_95_2DOF)

    assert 0.90 <= inside / trials <= 0.99


def test_uncertainty_region_grows_with_observation_noise() -> None:
    pixels = project(LANDMARKS_MM)

    tight = localise(make_atlas(), make_view(pixels, sigma_px=1.0), INTRINSICS)
    loose = localise(make_atlas(), make_view(pixels, sigma_px=4.0), INTRINSICS)

    assert tight.uncertainty is not None and loose.uncertainty is not None
    assert loose.uncertainty.ellipse.semi_major_px > 3 * tight.uncertainty.ellipse.semi_major_px


def test_uncertainty_region_grows_when_the_landmarks_bunch_together() -> None:
    """Four landmarks on one side pin the pose down worse than ten around it.

    This is the case a new viewpoint can fix, so it shows in pose_only.
    """
    pixels = project(LANDMARKS_MM)

    spread = localise(make_atlas(), make_view(pixels), INTRINSICS)
    bunched = localise(make_atlas(), make_view(pixels, seen=[0, 2, 5, 8]), INTRINSICS)

    assert spread.uncertainty is not None and bunched.uncertainty is not None
    assert (
        bunched.uncertainty.pose_only.semi_major_px
        > 1.5 * spread.uncertainty.pose_only.semi_major_px
    )


def test_pose_only_leaves_out_the_atlas_error_of_the_target() -> None:
    """A target known to 10 mm stays that uncertain from any viewpoint."""
    result = localise(
        make_atlas(target_sigma_mm=10.0), make_view(project(LANDMARKS_MM)), INTRINSICS
    )

    assert result.uncertainty is not None
    assert result.uncertainty.ellipse.semi_major_px > 5 * result.uncertainty.pose_only.semi_major_px


def test_uncertainty_region_repeats_with_the_same_seed() -> None:
    view = make_view(project(LANDMARKS_MM))

    first = localise(make_atlas(), view, INTRINSICS, seed=3)
    second = localise(make_atlas(), view, INTRINSICS, seed=3)

    assert first == second
