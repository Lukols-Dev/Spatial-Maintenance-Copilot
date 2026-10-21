"""Frames with printed markers become a view set's clicks, and the clicks an atlas with an oriented target."""

import json
from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from annotate_markers import main
from build_atlas import main as build_atlas
from smc_core.calibration import save_calibration
from smc_core.contracts import load_atlas, load_clicks
from smc_core.testing import (
    CAMERA_ID,
    INTRINSICS,
    MARKER_BOX_DEPTH_MM,
    MARKERS_MM,
    TAG_ID,
    calibration,
    rendered_marker_views,
    rig_board,
)
from smc_core.xray import target_box

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def frames(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("frames")
    for name, frame in rendered_marker_views(rig_board(), MARKERS_MM):
        assert cv.imwrite(str(folder / name), frame)
    return folder


@pytest.fixture
def folder(frames: Path, tmp_path: Path) -> Path:
    copy = tmp_path / "cabinet-markers"
    copy.mkdir()
    for path in frames.iterdir():
        (copy / path.name).write_bytes(path.read_bytes())
    return copy


def test_the_markers_of_every_frame_become_its_clicks(
    folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main([str(folder), "--camera-id", CAMERA_ID])

    clicks = load_clicks(folder / "clicks.json")
    assert clicks.camera_id == CAMERA_ID
    assert sorted(clicks.views) == [f"view_{index}.png" for index in range(8)]
    assert clicks.points[:4] == ["m50_0", "m50_1", "m50_2", "m50_3"]
    assert clicks.points[-5:] == ["target", "target_0", "target_1", "target_2", "target_3"]
    assert {"m50_0", "target", "target_3"} <= clicks.views["view_0.png"].keys()
    printed = capsys.readouterr().out
    assert "8 of 8 frames with markers" in printed
    assert f"target's tag {TAG_ID}:" in printed


def test_markers_on_a_part_that_opens_are_left_out_where_the_tag_shows(folder: Path) -> None:
    main([str(folder), "--camera-id", CAMERA_ID, "--moving", "50", "51"])

    views = load_clicks(folder / "clicks.json").views
    for marked in views.values():
        if "target" in marked:
            assert not {"m50_0", "m51_0"} & marked.keys()
    assert any("m50_0" in marked for marked in views.values() if "target" not in marked)


def test_clicks_made_before_are_kept_unless_forced(folder: Path) -> None:
    (folder / "clicks.json").write_text('{"camera_id": "x", "views": {}}')

    with pytest.raises(SystemExit, match="its clicks are kept"):
        main([str(folder), "--camera-id", CAMERA_ID])
    assert json.loads((folder / "clicks.json").read_text())["camera_id"] == "x"

    main([str(folder), "--camera-id", CAMERA_ID, "--force"])
    assert load_clicks(folder / "clicks.json").camera_id == CAMERA_ID


def test_only_landmark_markers_can_move(folder: Path) -> None:
    with pytest.raises(SystemExit, match="not landmark markers"):
        main([str(folder), "--camera-id", CAMERA_ID, "--moving", str(TAG_ID)])


def test_frames_without_markers_mark_nothing(tmp_path: Path) -> None:
    assert cv.imwrite(str(tmp_path / "blank.png"), np.full((1920, 1080), 255, np.uint8))

    with pytest.raises(SystemExit, match="no marker"):
        main([str(tmp_path), "--camera-id", CAMERA_ID])
    assert not (tmp_path / "clicks.json").exists()


def test_the_atlas_builder_turns_the_marked_frames_into_an_atlas_with_its_box(
    folder: Path, tmp_path: Path
) -> None:
    main([str(folder), "--camera-id", CAMERA_ID])
    intrinsics = tmp_path / "phone.yml"
    save_calibration(str(intrinsics), calibration(), INTRINSICS["image_size"], CAMERA_ID)
    out = tmp_path / "atlas.json"

    build_atlas(
        [
            str(folder),
            "--clicks", str(folder / "clicks.json"),
            "--intrinsics", str(intrinsics),
            "--board", "rig_board_a",
            "--rig", str(REPOSITORY / "calib" / "rig.yaml"),
            "--asset-id", "home-cabinet",
            "--target-id", "target",
            "--target-extent", "80", "50", str(MARKER_BOX_DEPTH_MM),
            "--target-tag-depth", str(MARKER_BOX_DEPTH_MM),
            "--click-sigma-px", "0.5",
            "--samples", "20",
            "--out", str(out),
        ]
    )  # fmt: skip

    atlas = load_atlas(out)
    assert len(atlas.landmarks) == 4 * (len(MARKERS_MM) - 1)
    np.testing.assert_allclose(atlas.target.position_mm, MARKERS_MM[TAG_ID].mean(axis=0), atol=1.5)
    np.testing.assert_allclose(
        np.ptp(target_box(atlas.target)[:, 2]), MARKER_BOX_DEPTH_MM, atol=1.5
    )
