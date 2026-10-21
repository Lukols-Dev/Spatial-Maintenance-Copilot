"""A frame of a camera or a video, localised from its markers, on the synthetic marked scene."""

import cv2 as cv
import numpy as np
import pytest
from smc_core.contracts import Action
from smc_core.frames import localise_frame
from smc_core.markers import marker_detector
from smc_core.testing import (
    INTRINSICS,
    MARKER_SET,
    MARKERS_MM,
    TAG_ID,
    VIEWPOINTS,
    camera_pose,
    marker_atlas,
    render,
    render_markers,
    rig_board,
)

WITHOUT_TAG = {marker: corners for marker, corners in MARKERS_MM.items() if marker != TAG_ID}


def frame(index: int, placed: dict[int, np.ndarray]) -> np.ndarray:
    rotation, tvec = camera_pose(*VIEWPOINTS[index])
    return render_markers(render(rig_board(), rotation, tvec), placed, rotation, tvec)


def run(picture: np.ndarray):  # type: ignore[no-untyped-def]
    return localise_frame(
        picture,
        "f1",
        marker_atlas(),
        INTRINSICS,
        marker_detector(MARKER_SET),
        MARKER_SET,
        0.5,
        samples=100,
    )


def test_a_closed_frame_is_localised_from_every_marker_and_decided() -> None:
    found = run(frame(0, WITHOUT_TAG))

    ids = [observation.landmark_id for observation in found.view.observations]
    assert {landmark_id.split("_")[0] for landmark_id in ids} == {
        f"m{marker}" for marker in WITHOUT_TAG
    }
    assert found.localisation.failure is None
    assert found.decision.action is Action.ACCEPT
    assert found.sighting is None
    assert (
        found.localisation.occluder is not None and found.localisation.occluder.panel_id == "door"
    )


def test_with_the_tag_in_sight_the_door_s_markers_are_left_out_and_the_target_is_checked() -> None:
    found = run(frame(0, MARKERS_MM))

    ids = {observation.landmark_id for observation in found.view.observations}
    assert not {f"m50_{corner}" for corner in range(4)} & ids
    assert found.sighting is not None
    assert found.sighting.error_px is not None and found.sighting.error_px < 3.0
    assert found.sighting.inside_95 is True
    assert len(found.sighting.tag_px) == 4


def test_a_frame_of_another_size_is_refused() -> None:
    with pytest.raises(ValueError):
        run(np.full((1080, 1920), 255, np.uint8))


def test_a_frame_measures_its_blur_on_its_markers_and_a_smeared_one_is_held_still() -> None:
    sharp = frame(0, WITHOUT_TAG)
    # A camera moving 9 px sideways during the exposure.
    smeared = cv.filter2D(sharp, -1, np.full((1, 9), 1 / 9, np.float32))

    still, moved = run(sharp), run(smeared)

    assert still.quality.markers == len(WITHOUT_TAG)
    assert still.quality.edge_width_px is not None and still.quality.edge_width_px < 4
    assert still.decision.checks[-1].name == "edge_width_px"
    assert moved.quality.edge_width_px is not None and moved.quality.edge_width_px > 8
    assert moved.localisation.failure is None
    assert moved.decision.action is Action.HOLD_STILL
