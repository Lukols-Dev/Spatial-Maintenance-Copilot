"""The asset's box found from the markers on its faces, the tape and the floor."""

from pathlib import Path

import numpy as np
import pytest
from fit_panels import BoxFit, fit_box, fit_face, main
from smc_core.contracts import Atlas, Landmark, Target, load_atlas

SIDE_MM = 40.0
# A cabinet 610 wide, 340 deep and 380 high, in the frame of a 5 mm board lying
# in front of it: x across, the front at y = -60 facing +y, z down, the floor at +5.
BOX_MIN = np.array([100.0, -400.0, -375.0])
BOX_MAX = np.array([710.0, -60.0, 5.0])
X, Y, Z = np.eye(3)
# Each marker: its top-left corner, and the directions to its right and down as
# printed, so that right x down points into the face it is stuck on.
MARKERS = {
    50: ((150.0, -60.0, -330.0), X, Z),
    51: ((620.0, -60.0, -330.0), X, Z),
    52: ((150.0, -60.0, -80.0), X, Z),
    53: ((620.0, -60.0, -80.0), X, Z),
    54: ((140.0, -110.0, -375.0), X, Y),
    55: ((630.0, -110.0, -375.0), X, Y),
    56: ((100.0, -110.0, -330.0), Y, Z),
    57: ((100.0, -110.0, -80.0), Y, Z),
    58: ((710.0, -70.0, -330.0), -Y, Z),
}


def cabinet(turn_deg: float = 0.0) -> Atlas:
    """The cabinet's markers as an atlas, the board turned by turn_deg about the vertical."""
    angle = np.radians(turn_deg)
    turn = np.array(
        [[np.cos(angle), -np.sin(angle), 0.0], [np.sin(angle), np.cos(angle), 0.0], [0, 0, 1]]
    )
    landmarks = []
    for marker, (origin, right, down) in MARKERS.items():
        start = np.array(origin)
        corners = [
            start,
            start + SIDE_MM * right,
            start + SIDE_MM * (right + down),
            start + SIDE_MM * down,
        ]
        for index, corner in enumerate(corners):
            x, y, z = turn @ corner
            landmarks.append(Landmark(id=f"m{marker}_{index}", position_mm=(x, y, z), sigma_mm=0.5))
    return Atlas(
        asset_id="cabinet",
        version="2",
        frame="board:rig_board_b",
        landmarks=landmarks,
        target=Target(
            id="target",
            position_mm=(400.0, -200.0, -100.0),
            sigma_mm=1.0,
            extent_mm=(150.0, 65.0, 140.0),
        ),
    )


def fitted(atlas: Atlas) -> BoxFit:
    return fit_box(
        fit_face(atlas, "flap", [50, 51, 52, 53]),
        fit_face(atlas, "top", [54, 55]),
        [fit_face(atlas, "left_side", [56, 57]), fit_face(atlas, "right_side", [58])],
        (610.0, 340.0, 380.0),
        floor_mm=5.0,
    )


def test_the_box_is_where_its_marked_faces_and_the_tape_put_it() -> None:
    box = fitted(cabinet())

    np.testing.assert_allclose(box.minimum, BOX_MIN, atol=1e-6)
    np.testing.assert_allclose(box.maximum, BOX_MAX, atol=1e-6)
    assert box.names == {
        "y+": "flap",
        "y-": "back",
        "z-": "top",
        "z+": "bottom",
        "x-": "left_side",
        "x+": "right_side",
    }
    assert box.width_mm == pytest.approx(610.0) and box.height_mm == pytest.approx(380.0)
    assert all(face.tilt_deg < 1e-6 and face.flatness_mm < 1e-6 for face in box.faces)


def test_a_board_lying_askew_shows_as_the_faces_tilt() -> None:
    box = fitted(cabinet(turn_deg=3.0))

    tilts = {face.panel: face.tilt_deg for face in box.faces}
    assert tilts["flap"] == pytest.approx(3.0) and tilts["left_side"] == pytest.approx(3.0)
    assert tilts["top"] == pytest.approx(0.0, abs=1e-6)


def test_faces_that_do_not_square_with_the_board_are_refused() -> None:
    atlas = cabinet()

    size = (610.0, 340.0, 380.0)

    with pytest.raises(ValueError, match="does the board lie flat"):
        fit_box(
            fit_face(atlas, "flap", [50]),
            fit_face(atlas, "top", [56]),
            [fit_face(atlas, "left_side", [57]), fit_face(atlas, "right_side", [58])],
            size,
            5.0,
        )
    with pytest.raises(ValueError, match="not square to the board"):
        fit_box(
            fit_face(atlas, "flap", [50]),
            fit_face(atlas, "top", [54]),
            [fit_face(atlas, "left_side", [56]), fit_face(atlas, "right_side", [51])],
            size,
            5.0,
        )
    with pytest.raises(ValueError, match="one and the id of the other"):
        fit_box(fit_face(atlas, "flap", [50]), fit_face(atlas, "top", [54]), [], size, 5.0)
    with pytest.raises(ValueError, match="none of the markers"):
        fit_face(atlas, "back", [59])


def test_one_marked_side_and_the_tape_give_the_other() -> None:
    atlas = cabinet()

    box = fit_box(
        fit_face(atlas, "flap", [50, 51, 52, 53]),
        fit_face(atlas, "top", [54, 55]),
        [fit_face(atlas, "left_side", [56, 57])],
        (610.0, 340.0, 380.0),
        5.0,
        other_side="right_side",
    )

    np.testing.assert_allclose(box.minimum, BOX_MIN, atol=1e-6)
    np.testing.assert_allclose(box.maximum, BOX_MAX, atol=1e-6)
    assert box.names["x+"] == "right_side"
    assert box.width_mm is None and box.height_mm == pytest.approx(380.0)


def test_the_panels_are_written_with_the_flap_markers_moving(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "cabinet.json"
    path.write_text(cabinet().model_dump_json(indent=2) + "\n")

    main(
        [
            str(path),
            "--size", "610", "340", "380",
            "--floor-mm", "5",
            "--front", "flap=50,51,52,53",
            "--top", "top=54,55",
            "--side", "left_side=56,57",
            "--other-side", "right_side",
            "--moving", "flap=m50,m51,m52,m53",
        ]
    )  # fmt: skip

    written = load_atlas(path)
    assert sorted(panel.id for panel in written.panels) == [
        "back",
        "bottom",
        "flap",
        "left_side",
        "right_side",
        "top",
    ]
    moving = {landmark.id for landmark in written.landmarks if landmark.moves_with == "flap"}
    assert moving == {f"m{marker}_{corner}" for marker in (50, 51, 52, 53) for corner in range(4)}
    printed = capsys.readouterr().out
    assert "width between the sides: 610 mm by the tape, one side marked" in printed
    assert "height from the floor: 380.0 mm by the markers, 380 by the tape, +0.0" in printed
