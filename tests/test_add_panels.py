"""Adding the box's faces to an atlas as panels, and nothing else."""

from pathlib import Path

import pytest
from add_panels import main
from smc_core.contracts import load_atlas
from smc_core.testing import scene_atlas


@pytest.fixture
def atlas_file(tmp_path: Path) -> Path:
    path = tmp_path / "home-cabinet.json"
    path.write_text(scene_atlas().model_dump_json(indent=2) + "\n")
    return path


BOX = ["--box", "-200", "-200", "0", "300", "400", "500"]


def test_the_named_faces_become_panels_and_the_rest_stays(atlas_file: Path) -> None:
    main([str(atlas_file), *BOX, "--face", "z-=door", "--face", "x+=side", "--version", "2"])

    written = load_atlas(atlas_file)
    assert [panel.id for panel in written.panels] == ["door", "side"]
    assert {corner[2] for corner in written.panels[0].corners_mm} == {0.0}
    assert written.version == "2"
    assert written.landmarks == scene_atlas().landmarks and written.target == scene_atlas().target


def test_new_panels_replace_the_old_ones(atlas_file: Path, tmp_path: Path) -> None:
    main([str(atlas_file), *BOX, "--face", "z-=door"])
    out = tmp_path / "other.json"

    main([str(atlas_file), *BOX, "--face", "y+=top", "--out", str(out)])

    assert [panel.id for panel in load_atlas(out).panels] == ["top"]
    assert [panel.id for panel in load_atlas(atlas_file).panels] == ["door"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--face", "front=door"], "expected FACE=ID"),
        (["--face", "z-=door", "--face", "z-=lid"], "a face is named twice"),
        (["--face", "z-=door", "--face", "x+=door"], "duplicate panel ids"),
    ],
)
def test_a_wrong_face_is_refused(
    atlas_file: Path, arguments: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main([str(atlas_file), *BOX, *arguments])

    assert message in str(stopped.value) + capsys.readouterr().err
    assert load_atlas(atlas_file).panels == []


def test_a_box_inside_out_is_refused(atlas_file: Path) -> None:
    with pytest.raises(SystemExit, match="is not above"):
        main(
            [
                str(atlas_file),
                "--box",
                "300",
                "400",
                "500",
                "-200",
                "-200",
                "0",
                "--face",
                "z-=door",
            ]
        )


def test_landmarks_on_a_panel_that_opens_move_with_it(atlas_file: Path) -> None:
    main(
        [
            str(atlas_file),
            *BOX,
            "--face",
            "z-=door",
            "--moving",
            "door=corner_top_left,handle_screw",
        ]
    )

    moving = {landmark.id: landmark.moves_with for landmark in load_atlas(atlas_file).landmarks}
    assert moving["corner_top_left"] == "door" and moving["handle_screw"] == "door"
    assert moving["box_on_top"] is None


def test_a_landmark_the_atlas_does_not_have_cannot_move(atlas_file: Path) -> None:
    with pytest.raises(SystemExit, match="no landmark 'hinge'"):
        main([str(atlas_file), *BOX, "--face", "z-=door", "--moving", "door=hinge"])


def test_landmarks_can_only_move_with_a_panel_of_the_atlas(atlas_file: Path) -> None:
    with pytest.raises(SystemExit, match="panels the atlas does not have"):
        main([str(atlas_file), *BOX, "--face", "z-=door", "--moving", "lid=handle_screw"])
