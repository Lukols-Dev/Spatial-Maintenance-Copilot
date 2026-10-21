"""What hides the target: the panel on the line of sight, and the target's box, on known geometry."""

import cv2 as cv
import numpy as np
import pytest
from smc_core.contracts import Atlas, LandmarkObservation, Panel, Pose, View
from smc_core.localise import localise
from smc_core.testing import (
    INTRINSICS,
    POINTS_MM,
    TARGET_ID,
    VIEWPOINTS,
    camera_pose,
    clicks_for,
    scene_atlas,
)
from smc_core.xray import (
    BOX_EDGES,
    BOX_SIGNS,
    box_corners,
    box_panels,
    crossed_panel,
    occluder,
    project_outline,
)

# A cabinet 600 x 400 x 372 mm, as the board frame sees it: the front at y = -34.
CABINET = ((154.0, -434.0, -372.0), (754.0, -34.0, 0.0))
NAMES = {"y+": "flap", "x-": "left", "x+": "right", "z-": "top", "y-": "back", "z+": "bottom"}
INSIDE = np.array([579.0, -152.0, -51.0])


def panels() -> list[Panel]:
    return box_panels(*CABINET, NAMES)


def test_a_box_has_eight_corners_and_twelve_edges() -> None:
    corners = box_corners((10.0, 20.0, 30.0), (2.0, 4.0, 6.0))

    assert corners.shape == (8, 3)
    np.testing.assert_allclose(corners.mean(axis=0), (10.0, 20.0, 30.0))
    np.testing.assert_allclose(corners[0], (9.0, 18.0, 27.0))
    assert len(BOX_EDGES) == 12
    for a, b in BOX_EDGES:
        assert np.count_nonzero(BOX_SIGNS[a] != BOX_SIGNS[b]) == 1


def test_the_faces_of_a_box_lie_on_its_sides() -> None:
    by_id = {panel.id: np.array(panel.corners_mm) for panel in panels()}

    assert sorted(by_id) == sorted(NAMES.values())
    assert np.all(by_id["flap"][:, 1] == -34.0)
    assert np.all(by_id["top"][:, 2] == -372.0)
    assert np.all(by_id["left"][:, 0] == 154.0)
    # In order around the face: consecutive corners differ along one axis only.
    for corners in by_id.values():
        for index in range(4):
            step = corners[(index + 1) % 4] - corners[index]
            assert np.count_nonzero(step) == 1


def test_only_known_faces_of_a_real_box_are_panels() -> None:
    with pytest.raises(ValueError, match="no such faces"):
        box_panels(*CABINET, {"front": "flap"})
    with pytest.raises(ValueError, match="is not above"):
        box_panels(CABINET[1], CABINET[0], NAMES)


@pytest.mark.parametrize(
    ("eye", "panel"),
    [
        ((450.0, 900.0, -600.0), "flap"),  # in front, at eye height
        ((-600.0, -250.0, -300.0), "left"),
        ((1500.0, -250.0, -300.0), "right"),
        ((450.0, -250.0, -1500.0), "top"),  # above: up is -z
    ],
)
def test_the_line_of_sight_crosses_the_face_turned_to_the_camera(
    eye: tuple[float, float, float], panel: str
) -> None:
    crossed = crossed_panel(np.array(eye), INSIDE, panels())

    assert crossed is not None and crossed.id == panel


def test_nothing_hides_a_point_outside_every_panel() -> None:
    assert (
        crossed_panel(np.array([450.0, 900.0, -600.0]), np.array([450.0, 400.0, -50.0]), panels())
        is None
    )
    only_top = [panel for panel in panels() if panel.id == "top"]
    assert crossed_panel(np.array([450.0, 900.0, -600.0]), INSIDE, only_top) is None


def pose_at(index: int) -> Pose:
    rotation, tvec = camera_pose(*VIEWPOINTS[index])
    rvec = np.ravel(cv.Rodrigues(rotation)[0])
    return Pose(
        rvec=(float(rvec[0]), float(rvec[1]), float(rvec[2])),
        tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
    )


def scene_with_door() -> Atlas:
    """The synthetic scene with a door between the cameras and the target, in the plane z = 300."""
    door = Panel(
        id="door",
        corners_mm=[
            (-300.0, -300.0, 300.0),
            (400.0, -300.0, 300.0),
            (400.0, 500.0, 300.0),
            (-300.0, 500.0, 300.0),
        ],
    )
    return scene_atlas().model_copy(update={"panels": [door]})


def test_the_occluder_is_outlined_where_the_camera_sees_it() -> None:
    atlas = scene_with_door()
    pose = pose_at(0)

    found = occluder(atlas.panels, atlas.target.position_mm, pose, INTRINSICS)

    assert found is not None and found.panel_id == "door"
    assert found.outline_px == project_outline(atlas.panels[0].corners_mm, pose, INTRINSICS)
    assert len(found.outline_px) == 4
    assert occluder([], atlas.target.position_mm, pose, INTRINSICS) is None


def test_an_outline_behind_the_camera_lands_nowhere() -> None:
    behind = [(0.0, 0.0, -10_000.0), (10.0, 0.0, -10_000.0), (0.0, 10.0, -10_000.0)]

    assert project_outline(behind, pose_at(0), INTRINSICS) is None


def test_a_localisation_names_the_panel_its_target_is_behind() -> None:
    atlas = scene_with_door()
    clicked = clicks_for(0.5).views["view_0.png"]
    view = View(
        view_id="view_0.png",
        camera_id=INTRINSICS["camera_id"],
        observations=[
            LandmarkObservation(landmark_id=point, pixel=clicked[point], sigma_px=1.0)
            for point in POINTS_MM
            if point != TARGET_ID
        ],
    )

    found = localise(atlas, view, INTRINSICS, samples=50)

    assert found.occluder is not None and found.occluder.panel_id == "door"
    assert localise(scene_atlas(), view, INTRINSICS, samples=50).occluder is None
    assert found.target is not None and len(found.target.corners_px) == 8
    corners = np.array(found.target.corners_px)
    hull = np.array(found.target.outline_px)
    assert hull.min(axis=0) == pytest.approx(corners.min(axis=0))
    assert hull.max(axis=0) == pytest.approx(corners.max(axis=0))


def test_an_atlas_names_each_panel_once() -> None:
    door = Panel(id="door", corners_mm=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])

    with pytest.raises(ValueError, match="duplicate panel ids"):
        Atlas.model_validate(scene_atlas().model_dump() | {"panels": [door.model_dump()] * 2})
