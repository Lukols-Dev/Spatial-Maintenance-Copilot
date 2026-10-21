"""Printed markers as landmarks: found where they land, named, and built into an atlas.

The frames are the synthetic scene's, with markers drawn at known places
(smc_core.testing.MARKERS_MM), so every corner and the target's box are known.
"""

from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from smc_core.atlas_build import _tag_rvec, build_atlas
from smc_core.board_pose import pose_views
from smc_core.contracts import Clicks
from smc_core.markers import (
    Detection,
    MarkerSet,
    clicks_of,
    detect,
    landmark_id,
    load_marker_set,
    mark_images,
    marker_detector,
    marker_points,
    marker_set_of,
    tag_centre,
    tag_point_ids,
)
from smc_core.testing import (
    CAMERA_ID,
    INTRINSICS,
    MARKER_BOX_DEPTH_MM,
    MARKER_SIDE_MM,
    MARKERS_MM,
    TAG_ID,
    VIEWPOINTS,
    camera_pose,
    project,
    render,
    render_markers,
    rendered_marker_views,
    rig_board,
)
from smc_core.xray import target_box

RIG_FILE = Path(__file__).resolve().parents[3] / "calib" / "rig.yaml"
MARKERS = MarkerSet(cv.aruco.DICT_5X5_100, tuple(range(50, 61)), TAG_ID, MARKER_SIDE_MM)
LANDMARK_MARKERS = [marker for marker in MARKERS_MM if marker != TAG_ID]
TARGET = "target"


@pytest.fixture(scope="module")
def frames() -> list[tuple[str, np.ndarray]]:
    return list(rendered_marker_views(rig_board(), MARKERS_MM))


def test_the_rig_file_names_the_printed_markers() -> None:
    found = load_marker_set(RIG_FILE)

    assert found.landmark_ids == tuple(range(50, 61))
    assert found.target_id == TAG_ID
    assert found.side_mm == 40.0
    assert found.dictionary_id == cv.aruco.DICT_5X5_100


def test_each_corner_is_found_where_it_lands_and_named_by_its_marker(
    frames: list[tuple[str, np.ndarray]],
) -> None:
    detector = marker_detector(MARKERS)
    _, frame = frames[0]
    rotation, tvec = camera_pose(*VIEWPOINTS[0])

    found = detect(detector, MARKERS, frame)

    assert sorted({key.rsplit("_", 1)[0] for key in found.landmarks}) == [
        f"m{marker}" for marker in LANDMARK_MARKERS
    ]
    for marker in LANDMARK_MARKERS:
        truth = project(MARKERS_MM[marker], rotation, tvec)
        for corner in range(4):
            assert (
                np.hypot(*(np.array(found.landmarks[landmark_id(marker, corner)]) - truth[corner]))
                < 1.5
            )
    assert found.tag is not None
    np.testing.assert_allclose(found.tag, project(MARKERS_MM[TAG_ID], rotation, tvec), atol=1.5)


def test_the_boards_markers_are_no_landmarks(frames: list[tuple[str, np.ndarray]]) -> None:
    found = detect(marker_detector(MARKERS), MARKERS, frames[0][1])

    # The rig board in every frame has markers of the same dictionary, 20 to 31.
    assert {int(key[1:].split("_")[0]) for key in found.landmarks} == set(LANDMARK_MARKERS)
    assert len(found.landmarks) == 4 * len(LANDMARK_MARKERS)


def test_markers_on_a_moving_part_are_left_out_while_the_tag_is_in_sight(
    frames: list[tuple[str, np.ndarray]],
) -> None:
    detector = marker_detector(MARKERS)
    with_tag = frames[0][1]
    without_tag = next(iter(rendered_marker_views(rig_board(), {50: MARKERS_MM[50]})))[1]

    assert landmark_id(50, 0) not in detect(detector, MARKERS, with_tag, moving=[50]).landmarks
    assert landmark_id(51, 0) in detect(detector, MARKERS, with_tag, moving=[50]).landmarks
    assert landmark_id(50, 0) in detect(detector, MARKERS, without_tag, moving=[50]).landmarks


def test_a_marker_seen_twice_is_trusted_nowhere() -> None:
    rotation, tvec = camera_pose(*VIEWPOINTS[0])
    twice = render_markers(
        render_markers(render(rig_board(), rotation, tvec), {50: MARKERS_MM[50]}, rotation, tvec),
        {50: MARKERS_MM[51]},
        rotation,
        tvec,
    )

    assert detect(marker_detector(MARKERS), MARKERS, twice).landmarks == {}


def test_the_tag_s_centre_is_where_its_diagonals_cross() -> None:
    rotation, tvec = camera_pose(*VIEWPOINTS[4])
    corners = project(MARKERS_MM[TAG_ID], rotation, tvec)
    tag = tuple((float(x), float(y)) for x, y in corners)

    centre = tag_centre(tag)  # type: ignore[arg-type]

    np.testing.assert_allclose(
        centre, project(MARKERS_MM[TAG_ID].mean(axis=0), rotation, tvec)[0], atol=1e-6
    )


def test_a_detection_reads_as_clicks_with_the_target_and_its_tag() -> None:
    tag = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))

    marked = clicks_of(Detection(landmarks={"m50_0": (1.0, 2.0)}, tag=tag), TARGET)

    assert marked == {
        "m50_0": (1.0, 2.0),
        TARGET: (5.0, 5.0),
        **dict(zip(tag_point_ids(TARGET), tag, strict=True)),
    }
    assert clicks_of(Detection(landmarks={}, tag=None), TARGET) == {}


def test_a_rig_without_a_measured_side_uses_the_nominal_one() -> None:
    rig = {
        "dictionary": "DICT_5X5_100",
        "markers": {"landmark_ids": [50, 52], "target_id": 70, "side_nominal_mm": 40},
    }

    assert marker_set_of(rig) == MarkerSet(cv.aruco.DICT_5X5_100, (50, 51, 52), 70, 40.0)
    with pytest.raises(KeyError):
        marker_set_of({"dictionary": "DICT_5X5_100", "markers": {"landmark_ids": [50, 52]}})


def test_the_points_of_a_marker_set_are_its_corners_then_the_target() -> None:
    points = marker_points(MARKERS, TARGET)

    assert len(points) == 4 * 11 + 5
    assert points[:5] == ["m50_0", "m50_1", "m50_2", "m50_3", "m51_0"]
    assert points[-5:] == [TARGET, *tag_point_ids(TARGET)]


def test_marked_images_are_the_clicks_of_each_frame_and_their_counts(
    frames: list[tuple[str, np.ndarray]],
) -> None:
    detector = marker_detector(MARKERS)
    blank = ("blank.png", np.full_like(frames[0][1], 255))

    marked = mark_images([*frames, blank], MARKERS, TARGET, moving=[50])

    assert marked.images == len(frames) + 1
    assert sorted(marked.views) == sorted(name for name, _ in frames)
    for name, frame in frames:
        assert marked.views[name] == clicks_of(detect(detector, MARKERS, frame, [50]), TARGET)
    with_tag = sum(TARGET in points for points in marked.views.values())
    assert marked.tag_images == with_tag > 0
    for marker in LANDMARK_MARKERS:
        seen = sum(landmark_id(marker, 0) in points for points in marked.views.values())
        assert marked.marker_images[marker] == seen
    assert not any("m50_0" in points for points in marked.views.values() if TARGET in points)
    assert marked.marker_images[50] > 0


# ---- an atlas from markers ---------------------------------------------------------


@pytest.fixture(scope="module")
def built(frames: list[tuple[str, np.ndarray]]):  # type: ignore[no-untyped-def]
    detector = marker_detector(MARKERS)
    clicks = Clicks(
        camera_id=CAMERA_ID,
        views={name: clicks_of(detect(detector, MARKERS, frame), TARGET) for name, frame in frames},
    )
    board = rig_board()
    poses = pose_views(
        frames,
        cv.aruco.CharucoDetector(board),
        board,
        INTRINSICS,
        np.random.default_rng(0),
        samples=50,
    )
    return build_atlas(
        poses,
        clicks,
        INTRINSICS,
        asset_id="home-cabinet",
        version="1",
        frame="board:rig_board_a",
        target_id=TARGET,
        target_extent_mm=(80.0, 50.0, MARKER_BOX_DEPTH_MM),
        click_sigma_px=0.5,
        target_centre_sigma_mm=1.0,
        target_tag_depth_mm=MARKER_BOX_DEPTH_MM,
    )


def test_every_marker_corner_becomes_a_landmark_where_it_is(built) -> None:  # type: ignore[no-untyped-def]
    atlas, _ = built
    by_id = {landmark.id: np.array(landmark.position_mm) for landmark in atlas.landmarks}

    assert sorted(by_id) == sorted(landmark_id(m, c) for m in LANDMARK_MARKERS for c in range(4))
    for marker in LANDMARK_MARKERS:
        for corner in range(4):
            np.testing.assert_allclose(
                by_id[landmark_id(marker, corner)], MARKERS_MM[marker][corner], atol=1.5
            )


def test_the_tag_places_the_target_and_turns_its_box(built) -> None:  # type: ignore[no-untyped-def]
    atlas, report = built
    tag = MARKERS_MM[TAG_ID]

    np.testing.assert_allclose(atlas.target.position_mm, tag.mean(axis=0), atol=1.5)
    assert set(tag_point_ids(TARGET)) <= set(report["points"])
    # The box stands behind the tag, away from the cameras (+z here), the tag on its face.
    corners = target_box(atlas.target)
    np.testing.assert_allclose(corners[:, 2].min(), tag[0, 2], atol=1.5)
    np.testing.assert_allclose(corners[:, 2].max(), tag[0, 2] + MARKER_BOX_DEPTH_MM, atol=1.5)
    np.testing.assert_allclose(np.ptp(corners[:, 0]), 80.0, atol=1.5)
    np.testing.assert_allclose(np.ptp(corners[:, 1]), 50.0, atol=1.5)


def test_without_a_depth_the_tag_orients_nothing_and_is_no_landmark(
    frames: list[tuple[str, np.ndarray]],
) -> None:
    detector = marker_detector(MARKERS)
    clicks = Clicks(
        camera_id=CAMERA_ID,
        views={name: clicks_of(detect(detector, MARKERS, frame), TARGET) for name, frame in frames},
    )
    board = rig_board()
    poses = pose_views(
        frames,
        cv.aruco.CharucoDetector(board),
        board,
        INTRINSICS,
        np.random.default_rng(0),
        samples=20,
    )

    atlas, _ = build_atlas(
        poses,
        clicks,
        INTRINSICS,
        asset_id="home-cabinet",
        version="1",
        frame="board:rig_board_a",
        target_id=TARGET,
        target_extent_mm=(80.0, 50.0, 60.0),
        click_sigma_px=0.5,
        target_centre_sigma_mm=1.0,
    )

    assert atlas.target.rvec == (0.0, 0.0, 0.0) and atlas.target.box_offset_mm == (0.0, 0.0, 0.0)
    assert not set(tag_point_ids(TARGET)) & {landmark.id for landmark in atlas.landmarks}


def test_a_tag_read_mirrored_orients_nothing() -> None:
    tag = MARKERS_MM[TAG_ID]
    rotation, tvec = camera_pose(*VIEWPOINTS[0])
    pose = {"rotation": rotation, "tvec": tvec}

    _tag_rvec(tag, [pose])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="faces away"):
        _tag_rvec(tag[[1, 0, 3, 2]], [pose])  # type: ignore[list-item]
