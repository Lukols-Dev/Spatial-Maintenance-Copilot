"""A frame of a camera or a video, localised from its markers, on the synthetic marked scene."""

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


def test_the_guidance_measures_the_way_to_the_guide_view() -> None:
    atlas = marker_atlas()
    poses = [camera_pose(*viewpoint) for viewpoint in VIEWPOINTS]
    guide = next(
        index
        for index, (rotation, tvec) in enumerate(poses)
        if np.allclose(tvec, atlas.guide_view.tvec_mm, atol=1.0)  # type: ignore[union-attr]
    )

    at_guide = run(frame(guide, WITHOUT_TAG)).guidance
    elsewhere = run(frame((guide + 1) % len(VIEWPOINTS), WITHOUT_TAG)).guidance

    assert at_guide is not None and elsewhere is not None
    assert at_guide.progress is not None and elsewhere.progress is not None
    assert at_guide.alignment_px is not None and at_guide.alignment_px < 5.0
    assert at_guide.progress > elsewhere.progress


def test_a_frame_of_another_size_is_refused() -> None:
    with pytest.raises(ValueError):
        run(np.full((1080, 1920), 255, np.uint8))
