"""A tripod's clip becomes a viewpoint and its truth: the still stretch before the panel opens, and the one after."""

from collections.abc import Sequence
from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
import viewpoint_clips
from smc_core.markers import marker_detector
from smc_core.testing import (
    MARKER_SET,
    MARKERS_MM,
    TAG_ID,
    VIEWPOINTS,
    camera_pose,
    render,
    render_markers,
    rig_board,
)
from viewpoint_clips import check_clip, compare_takes, main, still_stretches, write_frames

SHUT = {marker: corners for marker, corners in MARKERS_MM.items() if marker != TAG_ID}
# The panel open: marker 50 went with it, and the target's tag is in sight.
OPEN = {marker: corners for marker, corners in MARKERS_MM.items() if marker != 50}
MOVING = {50}


def scene(placed: dict[int, np.ndarray], turn: float = 0.0) -> np.ndarray:
    """The marked scene from the first viewpoint, the camera turned a little further by turn."""
    rvec, distance = VIEWPOINTS[0]
    rotation, tvec = camera_pose([rvec[0], rvec[1] + turn, rvec[2]], distance)
    frame = render_markers(render(rig_board(), rotation, tvec), placed, rotation, tvec)
    return cv.cvtColor(frame, cv.COLOR_GRAY2BGR) if frame.ndim == 2 else frame


def passer_by(frame: np.ndarray, step: int) -> np.ndarray:
    """Someone crossing the picture: a dark band, further along at every step."""
    crossed = frame.copy()
    crossed[:, 150 * step : 150 * step + 400] = 40
    return crossed


def write_clip(path: Path, frames: Sequence[np.ndarray]) -> Path:
    height, width = frames[0].shape[:2]
    writer = cv.VideoWriter(str(path), cv.VideoWriter.fourcc(*"MJPG"), 30.0, (width, height))
    for frame in frames:
        writer.write(frame)
    writer.release()
    return path


def opened_clip(path: Path, after: np.ndarray) -> Path:
    shut = scene(SHUT)
    return write_clip(
        path, [shut] * 12 + [passer_by(shut, step) for step in range(5)] + [after] * 12
    )


@pytest.fixture(autouse=True)
def short_stretches(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test clips last a second: three frames settle, three make a stretch."""
    monkeypatch.setattr(viewpoint_clips, "SETTLE_S", 0.1)
    monkeypatch.setattr(viewpoint_clips, "SHORTEST_S", 0.1)


def test_the_still_stretches_are_those_between_the_changes_less_the_settling() -> None:
    changes = [0.0, 0.1, 0.2, 0.1, 9.0, 9.0, 0.1, 0.1, 0.1, 0.1, 0.1]

    assert still_stretches(changes, settle=1, shortest=1) == [(1, 1), (7, 9)]
    assert still_stretches(changes, settle=1, shortest=2) == [(7, 9)]
    assert still_stretches([0.0, 9.0, 9.0], settle=0, shortest=1) == []


def test_a_spots_clip_gives_its_shut_frame_and_its_open_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clip = opened_clip(tmp_path / "T01.avi", scene(OPEN))

    check = check_clip(clip, marker_detector(MARKER_SET), MARKER_SET, MOVING)
    main([str(clip), "--out", str(tmp_path / "views"), "--moving", "50"])

    assert check.problems == [] and check.notes == []
    assert check.shut is not None and check.shut.detection.tag is None
    assert check.opened is not None and check.opened.detection.tag is not None
    assert check.shut.index < 12 < 17 <= check.opened.index
    assert check.shift_px is not None and check.shift_px < 0.2
    assert sorted(path.name for path in (tmp_path / "views").iterdir()) == [
        "T01_close.png",
        "T01_open.png",
    ]
    assert "wrote the frames of 1 clips" in capsys.readouterr().out


def test_a_camera_that_moved_while_the_panel_opened_is_a_problem(tmp_path: Path) -> None:
    clip = opened_clip(tmp_path / "T02.avi", scene(OPEN, turn=0.01))

    check = check_clip(clip, marker_detector(MARKER_SET), MARKER_SET, MOVING)

    assert check.shift_px is not None and check.shift_px > viewpoint_clips.MOVED_PX
    assert check.problems == [
        f"the camera moved {check.shift_px:.1f} px between the shut and the open frame"
    ]


def test_a_take_of_the_shut_panel_gives_its_shut_frame_only(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "T01_1.avi", [scene(SHUT)] * 12)

    main([str(clip), "--out", str(tmp_path / "views"), "--moving", "50"])

    assert [path.name for path in (tmp_path / "views").iterdir()] == ["T01_1_close.png"]


def test_a_panel_never_opened_is_a_problem_and_gives_no_truth(tmp_path: Path) -> None:
    clip = opened_clip(tmp_path / "T03.avi", scene(SHUT))

    check = check_clip(clip, marker_detector(MARKER_SET), MARKER_SET, MOVING)

    assert not check.has_truth
    assert check.problems == ["the panel's markers did not move: was the panel opened?"]
    with pytest.raises(SystemExit, match="1 clips have problems: T03"):
        main([str(clip), "--out", str(tmp_path / "views"), "--moving", "50"])
    assert [path.name for path in (tmp_path / "views").iterdir()] == ["T03_close.png"]


def test_frames_already_exported_are_kept_unless_forced(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "T01_1.avi", [scene(SHUT)] * 12)
    (tmp_path / "views").mkdir()
    (tmp_path / "views" / "T01_1_close.png").write_bytes(b"earlier")

    with pytest.raises(SystemExit, match="--force replaces them"):
        main([str(clip), "--out", str(tmp_path / "views")])
    main([str(clip), "--out", str(tmp_path / "views"), "--force"])

    assert (tmp_path / "views" / "T01_1_close.png").read_bytes() != b"earlier"


def test_a_clip_that_ends_with_the_panel_shut_again_keeps_its_open_stretch(tmp_path: Path) -> None:
    shut, opened = scene(SHUT), scene(OPEN)
    frames = (
        [shut] * 12
        + [passer_by(shut, step) for step in range(5)]
        + [opened] * 12
        + [passer_by(opened, step) for step in range(5)]
        + [shut] * 12
    )
    clip = write_clip(tmp_path / "T04.avi", frames)

    check = check_clip(clip, marker_detector(MARKER_SET), MARKER_SET, MOVING)

    assert len(check.stretches) == 3
    assert check.problems == [] and check.has_truth
    assert check.opened is not None and 17 <= check.opened.index < 29
    assert check.reclosed is not None and check.reclosed.index >= 34
    assert write_frames(check, tmp_path) == ["T04_close.png", "T04_open.png", "T04_2_close.png"]


def test_a_take_whose_camera_moved_from_its_spots_is_left_out(tmp_path: Path) -> None:
    spot = check_clip(
        opened_clip(tmp_path / "T05.avi", scene(OPEN)),
        marker_detector(MARKER_SET),
        MARKER_SET,
        MOVING,
    )
    still = check_clip(
        write_clip(tmp_path / "T05_1.avi", [scene(SHUT)] * 12),
        marker_detector(MARKER_SET),
        MARKER_SET,
        MOVING,
    )
    moved = check_clip(
        write_clip(tmp_path / "T05_2.avi", [scene(SHUT, turn=0.01)] * 12),
        marker_detector(MARKER_SET),
        MARKER_SET,
        MOVING,
    )

    compare_takes([spot, still, moved], set(MARKER_SET.landmark_ids) - MOVING)

    assert not still.dropped and still.shift_px is not None and still.shift_px < 0.2
    assert moved.dropped and moved.notes[-1].startswith("left out: the camera moved")
    assert write_frames(moved, tmp_path) == []


def test_with_only_the_panels_markers_in_sight_the_shut_frames_tell_a_still_camera(
    tmp_path: Path,
) -> None:
    """Too close for the markers off the panel: the two shut stretches agree on the panel's."""
    shut, opened = scene({50: MARKERS_MM[50]}), scene({TAG_ID: MARKERS_MM[TAG_ID]})
    frames = (
        [shut] * 12
        + [passer_by(shut, step) for step in range(5)]
        + [opened] * 12
        + [passer_by(opened, step) for step in range(5)]
        + [shut] * 12
    )
    clip = write_clip(tmp_path / "T06.avi", frames)

    check = check_clip(clip, marker_detector(MARKER_SET), MARKER_SET, MOVING)

    assert check.problems == [] and check.has_truth and check.reclosed is not None
    assert check.shift_px is None
    assert check.notes[-1].startswith("no marker off the panel when open; shut before and after")


def test_a_spot_that_never_sees_the_tag_takes_the_stretch_with_the_panel_open(
    tmp_path: Path,
) -> None:
    """Seen from a side the tag stays hidden; the panel's marker leaving tells the open stretch."""
    shut, opened = scene(SHUT), scene({k: v for k, v in SHUT.items() if k != 50})
    frames = (
        [shut] * 12
        + [passer_by(shut, step) for step in range(5)]
        + [opened] * 12
        + [passer_by(opened, step) for step in range(5)]
        + [shut] * 12
    )
    clip = write_clip(tmp_path / "T16.avi", frames)

    check = check_clip(clip, marker_detector(MARKER_SET), MARKER_SET, MOVING)

    assert check.problems == [] and not check.has_truth
    assert check.opened is not None and 17 <= check.opened.index < 29
    assert check.reclosed is not None
