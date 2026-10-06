import cv2 as cv
import numpy as np
import pytest
from smc_core.atlas_build import build_atlas
from smc_core.board_pose import ViewPose, board_view_pose, pose_views
from smc_core.contracts import Atlas, Clicks, LandmarkObservation, View
from smc_core.localise import localise
from smc_core.testing import (
    CAMERA_ID,
    EXTENT_MM,
    INTRINSICS,
    POINTS_MM,
    TARGET_ID,
    VIEWPOINTS,
    camera_pose,
    clicks_for,
    project,
    render,
    rendered_views,
    rig_board,
)
from smc_core.triangulate import locate_point


@pytest.fixture
def board() -> cv.aruco.CharucoBoard:
    return rig_board()


def posed_views(board: cv.aruco.CharucoBoard) -> dict[str, ViewPose]:
    detector = cv.aruco.CharucoDetector(board)
    poses = pose_views(rendered_views(board), detector, board, INTRINSICS, np.random.default_rng(0))
    assert len(poses) == len(VIEWPOINTS), "the board is not found from every viewpoint"
    return poses


def build(poses: dict[str, ViewPose], clicks: Clicks) -> tuple[Atlas, dict[str, object]]:
    atlas, report = build_atlas(
        poses,
        clicks,
        INTRINSICS,
        asset_id="cabinet",
        version="test",
        frame="board:rig_board_a",
        target_id=TARGET_ID,
        target_extent_mm=EXTENT_MM,
        click_sigma_px=1.0,
        target_centre_sigma_mm=5.0,
    )
    return atlas, dict(report)


def test_board_view_pose_recovers_the_camera(board: cv.aruco.CharucoBoard) -> None:
    detector = cv.aruco.CharucoDetector(board)
    rotation, tvec = camera_pose([0.3, -0.2, 0.05], 700.0)

    pose = board_view_pose(
        detector, board, render(board, rotation, tvec), INTRINSICS, np.random.default_rng(0)
    )

    assert pose is not None
    np.testing.assert_allclose(pose["rotation"], rotation, atol=0.01)
    np.testing.assert_allclose(pose["tvec"], tvec, atol=3.0)
    assert pose["corners"] == 15
    assert pose["rotation_samples"].shape == (200, 3, 3)


def test_board_view_pose_spread_follows_the_corner_sigma(board: cv.aruco.CharucoBoard) -> None:
    detector = cv.aruco.CharucoDetector(board)
    rotation, tvec = camera_pose([0.3, -0.2, 0.05], 700.0)
    frame = render(board, rotation, tvec)

    tight = board_view_pose(detector, board, frame, INTRINSICS, np.random.default_rng(0), 0.2)
    loose = board_view_pose(detector, board, frame, INTRINSICS, np.random.default_rng(0), 2.0)

    assert tight is not None and loose is not None
    assert loose["tvec_samples"].std(axis=0).sum() > 5 * tight["tvec_samples"].std(axis=0).sum()


def test_board_view_pose_returns_none_when_the_board_is_not_in_the_frame(
    board: cv.aruco.CharucoBoard,
) -> None:
    detector = cv.aruco.CharucoDetector(board)
    wall = np.full((1920, 1080, 3), 255, np.uint8)

    assert board_view_pose(detector, board, wall, INTRINSICS, np.random.default_rng(0)) is None


def test_board_view_pose_refuses_a_frame_of_another_size(board: cv.aruco.CharucoBoard) -> None:
    detector = cv.aruco.CharucoDetector(board)
    landscape = np.full((1080, 1920, 3), 255, np.uint8)

    with pytest.raises(ValueError, match="rotated by 90 degrees"):
        board_view_pose(detector, board, landscape, INTRINSICS, np.random.default_rng(0))


def test_pose_views_poses_the_frames_with_the_board_in_order(
    board: cv.aruco.CharucoBoard,
) -> None:
    detector = cv.aruco.CharucoDetector(board)
    first, second = list(rendered_views(board))[:2]
    wall = ("wall.png", np.full((1920, 1080, 3), 255, np.uint8))

    poses = pose_views([first, wall, second], detector, board, INTRINSICS, np.random.default_rng(3))

    # One generator, drawn from frame by frame: the same as posing them in turn.
    rng = np.random.default_rng(3)
    expected = [
        board_view_pose(detector, board, frame, INTRINSICS, rng) for _, frame in (first, second)
    ]
    assert list(poses) == [first[0], second[0]]
    for pose, single in zip(poses.values(), expected, strict=True):
        assert single is not None
        np.testing.assert_array_equal(pose["tvec_samples"], single["tvec_samples"])


def test_locate_point_needs_two_views(board: cv.aruco.CharucoBoard) -> None:
    poses = posed_views(board)
    pose = poses["view_0.png"]

    assert locate_point([(pose, (500.0, 900.0))], INTRINSICS, 1.0, np.random.default_rng(0)) is None


def test_build_atlas_places_every_point_within_its_own_sigma(
    board: cv.aruco.CharucoBoard,
) -> None:
    atlas, _ = build(posed_views(board), clicks_for(sigma_px=1.0))

    located = {landmark.id: landmark for landmark in atlas.landmarks}
    assert set(located) == set(POINTS_MM) - {TARGET_ID}
    for point_id, landmark in located.items():
        error = np.linalg.norm(np.array(landmark.position_mm) - POINTS_MM[point_id])
        assert error < 2 * landmark.sigma_mm * np.sqrt(3), point_id
        assert 0 < landmark.sigma_mm < 15, point_id

    error = np.linalg.norm(np.array(atlas.target.position_mm) - POINTS_MM[TARGET_ID])
    assert error < 2 * atlas.target.sigma_mm * np.sqrt(3)
    assert atlas.target.extent_mm == EXTENT_MM


def test_build_atlas_sigma_grows_with_click_noise(board: cv.aruco.CharucoBoard) -> None:
    poses = posed_views(board)

    sharp, _ = build(poses, clicks_for(sigma_px=0.5))
    noisier, _ = build_atlas(
        poses,
        clicks_for(sigma_px=0.5),
        INTRINSICS,
        asset_id="cabinet",
        version="test",
        frame="board",
        target_id=TARGET_ID,
        target_extent_mm=EXTENT_MM,
        click_sigma_px=4.0,
        target_centre_sigma_mm=5.0,
    )

    assert noisier.landmarks[0].sigma_mm > 2 * sharp.landmarks[0].sigma_mm


def test_build_atlas_is_repeatable_with_the_same_seed(board: cv.aruco.CharucoBoard) -> None:
    poses = posed_views(board)
    clicks = clicks_for(sigma_px=1.0)

    assert build(poses, clicks)[0] == build(poses, clicks)[0]


def test_build_atlas_skips_a_point_seen_in_one_view(board: cv.aruco.CharucoBoard) -> None:
    poses = posed_views(board)
    clicks = clicks_for(sigma_px=1.0)
    clicks.views["view_0.png"]["lone_point"] = (500.0, 900.0)

    atlas, report = build(poses, clicks)

    assert "lone_point" not in {landmark.id for landmark in atlas.landmarks}
    assert report["skipped"] == {"lone_point": "seen in 1 posed view, needs 2"}


def test_build_atlas_lists_views_in_which_the_board_was_not_found(
    board: cv.aruco.CharucoBoard,
) -> None:
    poses = posed_views(board)
    del poses["view_3.png"]

    _, report = build(poses, clicks_for(sigma_px=1.0))

    assert report["unposed_views"] == ["view_3.png"]


def test_build_atlas_fails_without_a_located_target(board: cv.aruco.CharucoBoard) -> None:
    poses = posed_views(board)
    clicks = clicks_for(sigma_px=1.0)
    for marked in clicks.views.values():
        del marked[TARGET_ID]

    with pytest.raises(ValueError, match="target 'drone' is not located: never clicked"):
        build(poses, clicks)


def test_build_atlas_refuses_clicks_from_another_camera(board: cv.aruco.CharucoBoard) -> None:
    poses = posed_views(board)
    clicks = clicks_for(sigma_px=1.0).model_copy(update={"camera_id": "phone-0.5x"})

    with pytest.raises(ValueError, match=r"phone-0\.5x"):
        build(poses, clicks)


def test_built_atlas_localises_a_new_view(board: cv.aruco.CharucoBoard) -> None:
    """The point of the atlas: a camera that never saw the board finds the target.

    From a new viewpoint only the landmarks are visible, the way the cabinet
    door hides the drone. The projected target must land near the truth.
    """
    atlas, _ = build(posed_views(board), clicks_for(sigma_px=1.0))
    rotation, tvec = camera_pose([0.1, 0.25, 0.0], 900.0)
    rng = np.random.default_rng(5)

    observations = []
    for landmark in atlas.landmarks:
        pixel = project(POINTS_MM[landmark.id], rotation, tvec)[0] + rng.normal(0, 1.0, 2)
        observations.append(
            LandmarkObservation(landmark_id=landmark.id, pixel=(pixel[0], pixel[1]), sigma_px=1.0)
        )
    view = View(view_id="new", camera_id=CAMERA_ID, observations=observations)

    result = localise(atlas, view, INTRINSICS)

    assert result.failure is None
    assert result.target is not None and result.uncertainty is not None
    truth = project(POINTS_MM[TARGET_ID], rotation, tvec)[0]
    offset = np.array(result.target.centre_px) - truth
    assert np.linalg.norm(offset) < result.uncertainty.ellipse.semi_major_px * 1.5
