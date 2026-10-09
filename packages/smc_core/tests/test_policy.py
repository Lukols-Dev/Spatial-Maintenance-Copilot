"""The decision: every check, every reason, and every branch of the action rules.

The scenes are built, not rendered. A pinhole camera without distortion looks
at the asset from a known pose, and each landmark is placed where that pose
projects it to a chosen pixel. A Localisation states the measurements a test
needs; decide() only reads them, and projects the atlas itself.
"""

import numpy as np
import pytest
from smc_core.calibration import Intrinsics
from smc_core.contracts import (
    Action,
    Atlas,
    Decision,
    Ellipse,
    Failure,
    Landmark,
    LandmarkObservation,
    Localisation,
    Policy,
    Pose,
    ProjectedTarget,
    Quality,
    Target,
    UncertaintyRegion,
    View,
)
from smc_core.localise import localise
from smc_core.policy import decide
from smc_core.pose import MIN_CORRESPONDENCES, in_frame

WIDTH, HEIGHT = 1000, 2000
FOCAL = 1000.0
DISTANCE_MM = 1000.0
INTRINSICS: Intrinsics = {
    "camera_id": "test-camera",
    "image_size": (WIDTH, HEIGHT),
    "camera_matrix": np.array([[FOCAL, 0.0, WIDTH / 2], [0.0, FOCAL, HEIGHT / 2], [0.0, 0.0, 1.0]]),
    "dist_coeffs": np.zeros(5),
    "rms": 0.5,
    "std_intrinsics": np.zeros(9),
}
# The camera looks along the asset's z axis from DISTANCE_MM in front of it.
POSE = Pose(rvec=(0.0, 0.0, 0.0), tvec_mm=(0.0, 0.0, DISTANCE_MM))

Pixel = tuple[float, float]

# Eight landmarks around the frame centre, their box half of the frame.
FRAMED: dict[str, Pixel | None] = {
    "top_left": (150.0, 300.0),
    "top": (500.0, 350.0),
    "top_right": (850.0, 300.0),
    "left": (180.0, 1000.0),
    "right": (820.0, 1000.0),
    "bottom_left": (150.0, 1700.0),
    "bottom": (500.0, 1650.0),
    "bottom_right": (850.0, 1700.0),
}
CHECKS = [
    "landmarks",
    "inliers",
    "inlier_ratio",
    "rms_reprojection_px",
    "image_coverage",
    "target_in_frame",
    "pose_stability",
    "region_ratio",
]


def atlas_at(pixels: dict[str, Pixel | None]) -> Atlas:
    """Landmarks where POSE projects them to these pixels; None puts one behind the camera."""
    landmarks = []
    for landmark_id, pixel in pixels.items():
        position = (0.0, 0.0, -2 * DISTANCE_MM)
        if pixel is not None:
            u, v = pixel
            x = (u - WIDTH / 2) * DISTANCE_MM / FOCAL
            y = (v - HEIGHT / 2) * DISTANCE_MM / FOCAL
            position = (x, y, 0.0)
        landmarks.append(Landmark(id=landmark_id, position_mm=position, sigma_mm=1.0))
    target = Target(id="drone", position_mm=(0.0, 0.0, 100.0), sigma_mm=5.0, extent_mm=(100.0,) * 3)
    return Atlas(asset_id="test", version="1", frame="test", landmarks=landmarks, target=target)


def view_of(ids: list[str]) -> View:
    observations = [LandmarkObservation(landmark_id=i, pixel=(1.0, 2.0), sigma_px=1.0) for i in ids]
    return View(view_id="view", camera_id="test-camera", observations=observations)


def measured(
    *,
    observed: int = 8,
    inliers: int = 8,
    rms_px: float = 0.5,
    coverage: float = 0.3,
    target_px: Pixel = (500.0, 1000.0),
    radius_px: float = 100.0,
    semi_major_px: float = 20.0,
    pose_only_px: float = 15.0,
    failed_samples: int = 0,
) -> Localisation:
    """A localisation at POSE with these measurements; the defaults pass every check."""
    return Localisation(
        view_id="view",
        quality=Quality(
            observed=observed,
            inliers=inliers,
            inlier_ratio=inliers / observed,
            outlier_ids=[],
            rms_reprojection_px=rms_px,
            max_reprojection_px=2 * rms_px,
            reprojection_px={},
            image_coverage=coverage,
            non_planarity=0.1,
        ),
        pose=POSE,
        target=ProjectedTarget(
            centre_px=target_px,
            depth_mm=DISTANCE_MM + 100.0,
            in_frame=in_frame(target_px, INTRINSICS["image_size"]),
            outline_px=[],
            radius_px=radius_px,
        ),
        uncertainty=UncertaintyRegion(
            confidence=0.95,
            covariance_px=((40.0, 0.0), (0.0, 60.0)),
            ellipse=Ellipse(semi_major_px=semi_major_px, semi_minor_px=10.0, angle_deg=90.0),
            pose_only=Ellipse(semi_major_px=pose_only_px, semi_minor_px=5.0, angle_deg=90.0),
            samples=500,
            failed_samples=failed_samples,
            seed=0,
        ),
    )


def decide_framed(
    localisation: Localisation,
    pixels: dict[str, Pixel | None] = FRAMED,
    seen: list[str] | None = None,
    policy: Policy | None = None,
) -> Decision:
    """decide() with an atlas at these pixels, every landmark seen unless `seen` says otherwise."""
    view = view_of(list(pixels) if seen is None else seen)
    if policy is None:
        return decide(localisation, view, atlas_at(pixels), INTRINSICS)
    return decide(localisation, view, atlas_at(pixels), INTRINSICS, policy)


# ---- accepting -------------------------------------------------------------------


def test_a_localisation_that_passes_every_check_is_accepted() -> None:
    decision = decide_framed(measured())

    assert decision.reliable
    assert decision.action is Action.ACCEPT
    assert decision.reasons == []
    assert decision.move_reason == ""
    assert [check.name for check in decision.checks] == CHECKS
    assert all(check.passed for check in decision.checks)
    assert decision.policy == Policy()


def test_each_check_holds_its_measurement_against_the_policy() -> None:
    decision = decide_framed(measured(failed_samples=10, semi_major_px=25.0))

    table = [(c.name, c.value, c.limit, c.op) for c in decision.checks]
    assert table == [
        ("landmarks", 8.0, 4.0, ">="),
        ("inliers", 8.0, 6.0, ">="),
        ("inlier_ratio", 1.0, 0.75, ">="),
        ("rms_reprojection_px", 0.5, 3.0, "<="),
        ("image_coverage", 0.3, 0.05, ">="),
        ("target_in_frame", 1.0, 1.0, ">="),
        ("pose_stability", 0.02, 0.05, "<="),
        ("region_ratio", 0.25, 0.5, "<="),
    ]


def test_a_measurement_on_its_limit_passes() -> None:
    decision = decide_framed(measured(inliers=6, observed=8, failed_samples=25, semi_major_px=50.0))

    assert [check.passed for check in decision.checks] == [True] * 8
    assert decision.action is Action.ACCEPT


def test_the_policy_sets_the_limits_and_travels_with_the_decision() -> None:
    strict = Policy(min_inliers=10, max_region_ratio=0.1)

    decision = decide_framed(measured(), policy=strict)

    assert not decision.reliable
    assert decision.policy == strict
    assert decision.reasons == [
        "8 inliers, needs ≥ 10",
        "95 % region is 0.20 \N{MULTIPLICATION SIGN} the target radius, needs ≤ 0.1",
    ]
    limits = {check.name: check.limit for check in decision.checks}
    assert (limits["inliers"], limits["region_ratio"]) == (10.0, 0.1)


def test_the_default_policy_needs_the_landmarks_pnp_needs() -> None:
    assert Policy().min_landmarks == MIN_CORRESPONDENCES


def test_the_same_localisation_gets_the_same_decision() -> None:
    localisation = measured(inliers=5)

    assert decide_framed(localisation) == decide_framed(localisation)


# ---- reasons ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("localisation", "reasons"),
    [
        (
            measured(inliers=5),
            ["5 inliers, needs ≥ 6", "inlier ratio 0.62, needs ≥ 0.75"],
        ),
        (
            measured(observed=8, inliers=1),
            ["1 inlier, needs ≥ 6", "inlier ratio 0.12, needs ≥ 0.75"],
        ),
        (measured(rms_px=3.4), ["RMS reprojection 3.40 px, needs ≤ 3 px"]),
        (measured(coverage=0.032), ["landmarks cover 3.2 % of the frame, needs ≥ 5 %"]),
        (
            measured(target_px=(-50.0, 1000.0)),
            ["the target centre projects outside the frame"],
        ),
        (
            measured(failed_samples=40),
            ["8.0 % of Monte Carlo samples failed, needs ≤ 5 %"],
        ),
        (
            measured(semi_major_px=62.0, pose_only_px=40.0),
            ["95 % region is 0.62 \N{MULTIPLICATION SIGN} the target radius, needs ≤ 0.5"],
        ),
    ],
)
def test_each_failed_check_gives_one_fact(localisation: Localisation, reasons: list[str]) -> None:
    decision = decide_framed(localisation)

    assert not decision.reliable
    assert decision.reasons == reasons


def test_a_value_just_short_of_its_limit_is_not_printed_as_the_limit() -> None:
    decision = decide_framed(measured(coverage=0.04996, rms_px=3.004))

    assert decision.reasons == [
        "RMS reprojection 3.004 px, needs ≤ 3 px",
        "landmarks cover 4.996 % of the frame, needs ≥ 5 %",
    ]


def test_a_target_without_area_cannot_be_judged() -> None:
    decision = decide_framed(measured(radius_px=0.0))

    region = decision.checks[-1]
    assert (region.value, region.passed) == (None, False)
    assert decision.reasons == ["region ratio cannot be computed"]


@pytest.mark.parametrize(
    ("semi_major_px", "pose_only_px", "dominates"),
    [(80.0, 30.0, True), (80.0, 40.0, False), (40.0, 5.0, False)],
)
def test_a_region_too_large_says_when_the_atlas_makes_it_so(
    semi_major_px: float, pose_only_px: float, dominates: bool
) -> None:
    """Below half of the region from the pose alone, no viewpoint can shrink it enough."""
    decision = decide_framed(measured(semi_major_px=semi_major_px, pose_only_px=pose_only_px))

    assert ("the atlas uncertainty dominates the region" in decision.reasons) is dominates


def test_the_atlas_share_is_reported_whatever_the_move() -> None:
    localisation = measured(target_px=(-50.0, 1000.0), semi_major_px=80.0, pose_only_px=10.0)

    decision = decide_framed(localisation)

    assert decision.action is Action.MOVE_LEFT
    assert decision.reasons[-1] == "the atlas uncertainty dominates the region"


# ---- rule 1: a failure -----------------------------------------------------------


def failed(failure: Failure, with_pose: bool = False, with_target: bool = False) -> Localisation:
    """A failure with what localise() keeps of it: the pose, and the target after posing."""
    full = measured()
    return Localisation(
        view_id="view",
        failure=failure,
        quality=full.quality if with_pose else None,
        pose=full.pose if with_pose else None,
        target=full.target if with_target else None,
    )


def test_too_few_landmarks_move_back_and_say_how_many_matched() -> None:
    """The decision of localise-result-failure.json, word for word."""
    localisation = failed(Failure.TOO_FEW_CORRESPONDENCES)

    decision = decide_framed(localisation, seen=["top", "left", "bottom_right"])

    assert not decision.reliable
    assert decision.action is Action.MOVE_BACK
    assert decision.move_reason == "too few landmarks in view to fit a pose"
    assert decision.reasons == [
        "localisation failed: too few correspondences",
        "3 landmarks matched, needs ≥ 4",
    ]
    assert [check.value for check in decision.checks] == [3.0] + [None] * 7
    assert not any(check.passed for check in decision.checks)


def test_only_landmarks_of_the_atlas_count_as_matched() -> None:
    view = view_of(["top", "left", "sticker", "door_logo"])

    decision = decide(failed(Failure.TOO_FEW_CORRESPONDENCES), view, atlas_at(FRAMED), INTRINSICS)

    assert decision.checks[0].value == 2.0
    assert decision.reasons[1] == "2 landmarks matched, needs ≥ 4"


@pytest.mark.parametrize(
    ("localisation", "action", "move_reason", "reasons"),
    [
        (
            failed(Failure.DEGENERATE_GEOMETRY),
            Action.MOVE_BACK,
            "the landmarks in view lie on one line",
            ["localisation failed: degenerate geometry"],
        ),
        (
            failed(Failure.PNP_FAILED),
            Action.MOVE_BACK,
            "no pose agrees with enough landmarks in view",
            ["localisation failed: PnP failed"],
        ),
        (
            failed(Failure.TARGET_BEHIND_CAMERA, with_pose=True),
            Action.MOVE_BACK,
            "the pose puts part of the target behind the camera",
            ["localisation failed: target behind the camera"],
        ),
        (
            failed(Failure.UNSTABLE_POSE, with_pose=True, with_target=True),
            Action.MOVE_CLOSER,
            "the pose is lost in almost every Monte Carlo sample",
            ["localisation failed: unstable pose"],
        ),
    ],
)
def test_a_failure_decides_the_move(
    localisation: Localisation, action: Action, move_reason: str, reasons: list[str]
) -> None:
    decision = decide_framed(localisation)

    assert not decision.reliable
    assert (decision.action, decision.move_reason) == (action, move_reason)
    assert decision.reasons == reasons


def test_a_failure_keeps_every_measurement_made_before_it() -> None:
    """An unstable pose still has its quality and its target; only the region is missing."""
    decision = decide_framed(failed(Failure.UNSTABLE_POSE, with_pose=True, with_target=True))

    values = {check.name: check.value for check in decision.checks}
    assert values == {
        "landmarks": 8.0,
        "inliers": 8.0,
        "inlier_ratio": 1.0,
        "rms_reprojection_px": 0.5,
        "image_coverage": 0.3,
        "target_in_frame": 1.0,
        "pose_stability": None,
        "region_ratio": None,
    }
    assert not decision.checks[-1].passed


def test_a_failure_decides_even_with_every_measured_check_passed() -> None:
    decision = decide_framed(failed(Failure.TARGET_BEHIND_CAMERA, with_pose=True))

    assert [check.passed for check in decision.checks[:5]] == [True] * 5
    assert not decision.reliable


# ---- rule 2: the target outside the frame ------------------------------------------


@pytest.mark.parametrize(
    ("target_px", "action", "edge"),
    [
        ((-50.0, 1000.0), Action.MOVE_LEFT, "left"),
        ((1100.0, 1000.0), Action.MOVE_RIGHT, "right"),
        ((500.0, -10.0), Action.MOVE_UP, "top"),
        ((500.0, 2100.0), Action.MOVE_DOWN, "bottom"),
        # Out past both edges: 600 px right is 1.2 half widths, 1050 px up 1.05
        # half heights, so the horizontal offset is the larger one.
        ((1100.0, -50.0), Action.MOVE_RIGHT, "right"),
        ((1040.0, -400.0), Action.MOVE_UP, "top"),
    ],
)
def test_a_target_outside_the_frame_is_followed(
    target_px: Pixel, action: Action, edge: str
) -> None:
    decision = decide_framed(measured(target_px=target_px))

    assert decision.action is action
    assert decision.move_reason == f"the target centre projects beyond the {edge} edge of the frame"


def test_the_target_comes_before_the_framing() -> None:
    """The landmarks extend beyond the left edge, but the target lies to the right."""
    pixels = {**FRAMED, "far_left": (-300.0, 900.0), "further_left": (-200.0, 1200.0)}

    decision = decide_framed(measured(target_px=(1200.0, 1000.0)), pixels)

    assert decision.action is Action.MOVE_RIGHT


# ---- rule 3: the framing of every landmark -----------------------------------------


@pytest.mark.parametrize(
    ("outside", "action", "edge"),
    [
        ([(-100.0, 500.0), (-50.0, 1500.0)], Action.MOVE_LEFT, "left"),
        ([(1100.0, 500.0), (1300.0, 1500.0)], Action.MOVE_RIGHT, "right"),
        ([(300.0, -100.0), (700.0, -10.0)], Action.MOVE_UP, "top"),
        ([(300.0, 2050.0), (700.0, 2500.0)], Action.MOVE_DOWN, "bottom"),
        # Two of three beyond the left edge are more than half.
        ([(-100.0, 500.0), (-50.0, 1500.0), (500.0, -30.0)], Action.MOVE_LEFT, "left"),
        # Beyond the top left corner, but further beyond the top.
        ([(-20.0, -400.0)], Action.MOVE_UP, "top"),
    ],
)
def test_landmarks_beyond_one_edge_bring_a_move_toward_it(
    outside: list[Pixel], action: Action, edge: str
) -> None:
    pixels = {**FRAMED, **{f"out_{index}": pixel for index, pixel in enumerate(outside)}}

    decision = decide_framed(measured(inliers=5), pixels)

    assert decision.action is action
    assert decision.move_reason == f"landmarks extend beyond the {edge} edge of the frame"


def test_the_framing_counts_landmarks_nobody_observed() -> None:
    """Only the framed landmarks were clicked; the pose still puts two beyond the left edge."""
    pixels = {**FRAMED, "hinge_top": (-120.0, 400.0), "hinge_bottom": (-90.0, 1600.0)}

    decision = decide_framed(measured(inliers=5), pixels, seen=list(FRAMED))

    assert decision.action is Action.MOVE_LEFT


@pytest.mark.parametrize(
    ("outside", "move_reason"),
    [
        ([(-100.0, 500.0), (1100.0, 500.0)], "landmarks extend beyond several edges of the frame"),
        ([None, None], "some landmarks lie behind the camera"),
        # Behind the camera is outside on no side, so one beyond the left edge
        # is not more than half of the two outside.
        ([(-100.0, 500.0), None], "some landmarks lie behind the camera"),
    ],
)
def test_landmarks_outside_on_no_single_side_bring_a_step_back(
    outside: list[Pixel | None], move_reason: str
) -> None:
    pixels = {**FRAMED, **{f"out_{index}": pixel for index, pixel in enumerate(outside)}}

    decision = decide_framed(measured(inliers=5), pixels)

    assert decision.action is Action.MOVE_BACK
    assert decision.move_reason == move_reason


def test_a_landmark_behind_the_camera_does_not_hide_a_majority() -> None:
    outside = {"out_0": (-100.0, 500.0), "out_1": (-80.0, 900.0), "behind": None}

    decision = decide_framed(measured(inliers=5), {**FRAMED, **outside})

    assert decision.action is Action.MOVE_LEFT


def test_landmarks_bunched_in_the_frame_bring_a_move_closer() -> None:
    bunched: dict[str, Pixel | None] = {
        "a": (400.0, 800.0),
        "b": (600.0, 800.0),
        "c": (400.0, 1200.0),
        "d": (600.0, 1200.0),
    }

    decision = decide_framed(measured(inliers=5), bunched)

    assert decision.action is Action.MOVE_CLOSER
    assert decision.move_reason == "landmarks fill 4 % of the frame"


def test_a_fill_just_below_a_quarter_is_not_printed_as_a_quarter() -> None:
    box: dict[str, Pixel | None] = {"a": (100.0, 500.0), "b": (600.0, 1496.0)}

    decision = decide_framed(measured(inliers=5), box)

    assert decision.action is Action.MOVE_CLOSER
    assert decision.move_reason == "landmarks fill 24.9 % of the frame"


@pytest.mark.parametrize(
    ("corners", "action", "side"),
    [
        ([(5.0, 100.0), (475.0, 1900.0)], Action.MOVE_LEFT, "left of"),
        ([(525.0, 100.0), (995.0, 1900.0)], Action.MOVE_RIGHT, "right of"),
        ([(50.0, 10.0), (950.0, 950.0)], Action.MOVE_UP, "above"),
        ([(50.0, 1050.0), (950.0, 1990.0)], Action.MOVE_DOWN, "below"),
    ],
)
def test_landmarks_off_the_frame_centre_bring_a_move_toward_them(
    corners: list[Pixel], action: Action, side: str
) -> None:
    (left, top), (right, bottom) = corners
    box: dict[str, Pixel | None] = {
        "a": (left, top),
        "b": (right, top),
        "c": (left, bottom),
        "d": (right, bottom),
    }

    decision = decide_framed(measured(inliers=5), box)

    assert decision.action is action
    assert decision.move_reason == f"landmarks sit {side} the frame centre"


def test_landmarks_framed_well_bring_a_move_closer() -> None:
    decision = decide_framed(measured(inliers=5))

    assert decision.action is Action.MOVE_CLOSER
    assert decision.move_reason == "landmarks fill 49 % of the frame"


# ---- with localise() ---------------------------------------------------------------


def project(atlas: Atlas, ids: list[str]) -> View:
    """The landmarks as the camera at POSE sees them, without noise."""
    by_id = {landmark.id: landmark for landmark in atlas.landmarks}
    observations = []
    for landmark_id in ids:
        x, y, z = by_id[landmark_id].position_mm
        depth = z + DISTANCE_MM
        pixel = (FOCAL * x / depth + WIDTH / 2, FOCAL * y / depth + HEIGHT / 2)
        observations.append(LandmarkObservation(landmark_id=landmark_id, pixel=pixel, sigma_px=1.0))
    return View(view_id="view", camera_id="test-camera", observations=observations)


def test_a_localised_view_of_every_landmark_is_accepted() -> None:
    atlas = atlas_at(FRAMED)
    view = project(atlas, list(FRAMED))

    decision = decide(localise(atlas, view, INTRINSICS, samples=200), view, atlas, INTRINSICS)

    assert decision.action is Action.ACCEPT, decision.reasons


def test_a_localised_view_of_five_landmarks_asks_for_more() -> None:
    atlas = atlas_at(FRAMED)
    view = project(atlas, ["top_left", "top_right", "left", "bottom_left", "bottom_right"])

    decision = decide(localise(atlas, view, INTRINSICS, samples=200), view, atlas, INTRINSICS)

    assert not decision.reliable
    assert decision.reasons == ["5 inliers, needs ≥ 6"]
    assert decision.action is Action.MOVE_CLOSER
