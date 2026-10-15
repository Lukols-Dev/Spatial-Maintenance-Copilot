"""Giving an older atlas its guide view from the frames it was built from."""

from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from guide_view import main
from smc_core.calibration import save_calibration
from smc_core.contracts import load_atlas
from smc_core.testing import (
    CAMERA_ID,
    INTRINSICS,
    VIEWPOINTS,
    calibration,
    camera_pose,
    clicks_for,
    rendered_views,
    rig_board,
    scene_atlas,
)

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    views = tmp_path / "views"
    views.mkdir()
    for name, frame in rendered_views(rig_board()):
        assert cv.imwrite(str(views / name), frame)
    (views / "clicks.json").write_text(clicks_for(0.5).model_dump_json())
    (tmp_path / "intrinsics").mkdir()
    save_calibration(
        str(tmp_path / "intrinsics" / "phone.yml"),
        calibration(),
        INTRINSICS["image_size"],
        CAMERA_ID,
    )
    (tmp_path / "atlas.json").write_text(scene_atlas().model_dump_json())
    return tmp_path


def run(workspace: Path) -> None:
    main(
        [
            str(workspace / "atlas.json"),
            str(workspace / "views"),
            "--intrinsics",
            str(workspace / "intrinsics"),
            "--rig",
            str(REPOSITORY / "calib" / "rig.yaml"),
        ]
    )


def test_the_atlas_gets_a_recorded_pose_as_its_guide_view(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(workspace)

    atlas = load_atlas(workspace / "atlas.json")
    assert atlas.guide_view is not None
    true_tvecs = [camera_pose(*viewpoint)[1] for viewpoint in VIEWPOINTS]
    assert (
        min(np.linalg.norm(np.array(atlas.guide_view.tvec_mm) - tvec) for tvec in true_tvecs) < 5.0
    )
    assert "one of 8 posed frames" in capsys.readouterr().out
    assert atlas.landmarks == scene_atlas().landmarks


def test_an_atlas_not_framed_by_a_board_has_no_guide_view(workspace: Path) -> None:
    (workspace / "atlas.json").write_text(
        scene_atlas().model_copy(update={"frame": "synthetic"}).model_dump_json()
    )

    with pytest.raises(SystemExit, match="not a rig board"):
        run(workspace)
