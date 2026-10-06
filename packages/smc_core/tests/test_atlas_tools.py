from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from build_atlas import main as build_atlas_main
from export_views import main as export_views_main
from smc_core.calibration import save_calibration
from smc_core.contracts import load_atlas
from smc_core.testing import (
    CAMERA_ID,
    INTRINSICS,
    POINTS_MM,
    TARGET_ID,
    calibration,
    clicks_for,
    rendered_views,
    rig_board,
)

RIG = """\
dictionary: DICT_5X5_100
marker_ratio: 0.72
boards:
  rig_board_a:
    squares_x: 4
    squares_y: 6
    ids: [20, 31] # inclusive range
    square_nominal_mm: 25.0
    marker_nominal_mm: 18.0
    square_measured_mm: {square}
    marker_measured_mm: null
    measurement_uncertainty_mm: 0.25
"""


def write_session(folder: Path, square: str = "25.0") -> dict[str, Path]:
    """Views of the board, the marked points, the calibration and the rig file."""
    views = folder / "views"
    views.mkdir()
    for name, frame in rendered_views(rig_board()):
        cv.imwrite(str(views / name), frame)

    save_calibration(str(folder / "camera.yml"), calibration(), INTRINSICS["image_size"], CAMERA_ID)

    (folder / "clicks.json").write_text(clicks_for(1.0).model_dump_json(), encoding="utf-8")
    (folder / "rig.yaml").write_text(RIG.format(square=square), encoding="utf-8")
    return {
        "views": views,
        "clicks": folder / "clicks.json",
        "intrinsics": folder / "camera.yml",
        "rig": folder / "rig.yaml",
        "out": folder / "atlas" / "cabinet.json",
    }


def atlas_arguments(files: dict[str, Path]) -> list[str]:
    return [
        str(files["views"]),
        "--clicks", str(files["clicks"]),
        "--intrinsics", str(files["intrinsics"]),
        "--rig", str(files["rig"]),
        "--board", "rig_board_a",
        "--asset-id", "cabinet",
        "--target-id", TARGET_ID,
        "--target-extent", "300", "300", "100",
        "--out", str(files["out"]),
    ]  # fmt: skip


def test_build_atlas_writes_an_atlas_that_loads_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = write_session(tmp_path)

    build_atlas_main([*atlas_arguments(files), "--target-measured", "60", "90", "420"])

    atlas = load_atlas(files["out"])
    assert atlas.asset_id == "cabinet"
    assert atlas.frame == "board:rig_board_a"
    assert len(atlas.landmarks) == len(POINTS_MM) - 1
    error = np.linalg.norm(np.array(atlas.target.position_mm) - POINTS_MM[TARGET_ID])
    assert error < 5.0

    report = capsys.readouterr().out
    assert "views with the board: 8" in report
    assert "<- target" in report
    assert "mm between the triangulated and the measured position" in report


def test_build_atlas_stops_when_the_board_was_never_measured(tmp_path: Path) -> None:
    files = write_session(tmp_path, square="null")

    with pytest.raises(SystemExit, match="square_measured_mm"):
        build_atlas_main(atlas_arguments(files))

    assert not files["out"].exists()


def test_export_views_writes_the_sharpest_frame_of_every_window(tmp_path: Path) -> None:
    clip = tmp_path / "clip.avi"
    writer = cv.VideoWriter(str(clip), cv.VideoWriter.fourcc(*"MJPG"), 30.0, (64, 48))
    pattern = np.kron([[0, 255], [255, 0]], np.ones((6, 8))).astype(np.uint8)
    sharp = cv.cvtColor(np.tile(pattern, (4, 4)), cv.COLOR_GRAY2BGR)
    for index in range(6):
        writer.write(sharp if index in (1, 4) else cv.GaussianBlur(sharp, (0, 0), 3))
    writer.release()

    export_views_main([str(clip), "--out", str(tmp_path / "views"), "--window", "3"])

    assert sorted(path.name for path in (tmp_path / "views").iterdir()) == [
        "frame_000001.png",
        "frame_000004.png",
    ]


def test_export_views_converts_a_folder_of_photos_to_png(tmp_path: Path) -> None:
    photos = tmp_path / "photos"
    photos.mkdir()
    cv.imwrite(str(photos / "IMG_1.jpg"), np.zeros((40, 30, 3), np.uint8))

    export_views_main([str(photos), "--out", str(tmp_path / "views")])

    exported = cv.imread(str(tmp_path / "views" / "IMG_1.png"))
    assert exported.shape == (40, 30, 3)
