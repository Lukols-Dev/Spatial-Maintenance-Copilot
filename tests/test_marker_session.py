"""A session's videos get their roles from the card, checked against them, and a verdict reads the numbers."""

from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from marker_session import (
    CARD,
    DISAGREE_PX,
    Glance,
    Verdict,
    disagreeing_frames,
    folder_of,
    leave_out,
    main,
    recording_order,
    role_problems,
)
from smc_core.contracts import Clicks
from smc_core.markers import clicks_of, detect, marker_detector
from smc_core.testing import (
    INTRINSICS,
    MARKER_SET,
    MARKERS_MM,
    TAG_ID,
    rendered_marker_views,
    rig_board,
)


def glance(tags: list[bool], rig_board: int = 12, calibration_board: int = 0) -> Glance:
    return Glance(
        seconds=10.0,
        frames=len(tags),
        calibration_board=calibration_board,
        rig_board=rig_board,
        tags=tags,
    )


def test_videos_sort_as_the_phone_numbered_them() -> None:
    names = ["IMG_0812.MOV", "IMG_0799.MOV", "IMG_0812 2.MOV", "IMG_1003.MOV"]

    ordered = sorted((Path(name) for name in names), key=recording_order)

    assert [path.name for path in ordered] == [
        "IMG_0799.MOV",
        "IMG_0812 2.MOV",
        "IMG_0812.MOV",
        "IMG_1003.MOV",
    ]


def test_the_card_puts_every_role_in_its_folder() -> None:
    assert CARD[:3] == ("atlas_close", "atlas_open", "T01") and len(CARD) == 14
    assert [folder_of(role) for role in ("calib", "atlas_open", "T05", "T05_1")] == [
        "calib",
        "atlas",
        "tripod",
        "tripod",
    ]


@pytest.mark.parametrize(
    ("role", "seen", "problems"),
    [
        ("calib", glance([False] * 12, rig_board=0, calibration_board=10), []),
        ("calib", glance([False] * 12, rig_board=0, calibration_board=2), ["the calibration board is in few frames"]),
        ("atlas_close", glance([False] * 12), []),
        ("atlas_close", glance([False] * 11 + [True]), ["the tag is in sight: was the panel shut?"]),
        ("atlas_open", glance([False] * 12, rig_board=3), ["the rig board is in few frames", "the tag is never in sight: was the panel open?"]),
        ("T01", glance([False] * 8 + [True] * 4), []),
        ("T01", glance([True] * 12), ["the tag is in sight at the start: was the panel shut?"]),
        ("T02", glance([False] * 12), ["the tag is not in sight at the end: opened, with the tag in view?"]),
        ("T11", glance([False] * 12), []),
        ("T01_1", glance([False] * 12), []),
        ("T01_1", glance([False] * 6 + [True] * 6), ["the tag is in sight in a take of the shut panel"]),
    ],
)  # fmt: skip
def test_a_glance_that_does_not_fit_its_role_is_a_problem(
    role: str, seen: Glance, problems: list[str]
) -> None:
    assert role_problems(role, seen, {"T11"}) == problems


def test_the_verdict_puts_what_to_record_again_first() -> None:
    assert Verdict().format().startswith("GO:")
    held = Verdict(hold=["a number"], notes=["a fact"])
    assert held.format().splitlines() == [
        "HOLD: look at these before the rig board is moved:",
        "  look: a number",
        "  note: a fact",
    ]
    assert Verdict(rerecord=["T07"], hold=["a number"]).format().startswith("RE-RECORD")


def blank_clip(path: Path) -> Path:
    writer = cv.VideoWriter(str(path), cv.VideoWriter.fourcc(*"MJPG"), 30.0, (64, 48))
    for _ in range(6):
        writer.write(np.zeros((48, 64, 3), np.uint8))
    writer.release()
    return path


def test_sort_names_the_roles_and_moves_only_when_asked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    blank_clip(incoming / "IMG_0002.avi")
    blank_clip(incoming / "IMG_0001.avi")
    (incoming / "IMG_0003.HEIC").write_bytes(b"a photo, not a video")
    session = tmp_path / "session"
    arguments = ["sort", str(incoming), str(session), "--roles", "T11,T11_1"]

    main(arguments)
    assert "every video fits its role; --apply moves them" in capsys.readouterr().out
    assert not session.exists()

    main([*arguments, "--apply"])
    assert sorted(path.relative_to(session).as_posix() for path in session.rglob("*.avi")) == [
        "tripod/T11.avi",
        "tripod/T11_1.avi",
    ]


def test_sort_refuses_videos_that_do_not_fit_or_do_not_count_up(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    blank_clip(incoming / "IMG_0001.avi")
    session = tmp_path / "session"

    with pytest.raises(SystemExit, match="1 videos do not fit their roles: nothing moved"):
        main(["sort", str(incoming), str(session), "--roles", "calib"])
    with pytest.raises(SystemExit, match=r"1 videos in .*, 14 roles on the card"):
        main(["sort", str(incoming), str(session)])
    assert not session.exists()


def test_a_frame_whose_pose_disagrees_with_the_others_is_left_out(tmp_path: Path) -> None:
    """Every frame sees the markers where the others put them, but one is 40 px off."""
    placed = {marker: corners for marker, corners in MARKERS_MM.items() if marker != TAG_ID}
    detector = marker_detector(MARKER_SET)
    views = {}
    for name, frame in rendered_marker_views(rig_board(), placed):
        cv.imwrite(str(tmp_path / name), frame)
        views[name] = clicks_of(detect(detector, MARKER_SET, frame), "target")
    views["view_3.png"] = {point: (x + 40.0, y) for point, (x, y) in views["view_3.png"].items()}
    clicks = Clicks(camera_id="phone-1x-portrait", views=views)

    disagreeing, typical = disagreeing_frames(tmp_path, clicks, INTRINSICS, rig_board())
    kept = leave_out(tmp_path, clicks, sorted(disagreeing))

    assert list(disagreeing) == ["view_3.png"] and disagreeing["view_3.png"] > DISAGREE_PX
    assert typical < 2.0
    assert "view_3.png" not in kept.views and not (tmp_path / "view_3.png").exists()
    assert Clicks.model_validate_json((tmp_path / "clicks.json").read_text()).views == kept.views
