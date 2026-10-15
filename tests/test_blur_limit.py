"""The blur limit's evidence: the target's jitter against the markers' edge width, on a video."""

from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from blur_limit import jitter, main
from smc_core.calibration import save_calibration
from smc_core.testing import (
    CAMERA_ID,
    INTRINSICS,
    MARKERS_MM,
    TAG_ID,
    calibration,
    marker_atlas,
    rendered_marker_views,
    rig_board,
)

REPOSITORY = Path(__file__).resolve().parents[1]
WITHOUT_TAG = {marker: corners for marker, corners in MARKERS_MM.items() if marker != TAG_ID}


def test_a_smooth_path_has_no_jitter_and_a_jump_has_its_size() -> None:
    assert jitter([(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]) == [None, 0.0, None]
    assert jitter([(0.0, 0.0), (3.0, 4.0), (0.0, 0.0), None, (1.0, 1.0)]) == [
        None,
        5.0,
        None,
        None,
        None,
    ]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """The synthetic marked scene as a video, its second half smeared, with its camera and atlas."""
    # The scene is drawn in grey; a video holds colour frames.
    frames = [
        cv.cvtColor(frame, cv.COLOR_GRAY2BGR) if frame.ndim == 2 else frame
        for _, frame in rendered_marker_views(rig_board(), WITHOUT_TAG)
    ]
    height, width = frames[0].shape[:2]
    writer = cv.VideoWriter(
        str(tmp_path / "walk.avi"), cv.VideoWriter.fourcc(*"MJPG"), 30.0, (width, height)
    )
    smear = np.full((1, 11), 1 / 11, np.float32)
    for frame in frames[:4] + [cv.filter2D(frame, -1, smear) for frame in frames[4:]]:
        writer.write(frame)
    writer.release()
    (tmp_path / "intrinsics").mkdir()
    save_calibration(
        str(tmp_path / "intrinsics" / "phone.yml"),
        calibration(),
        INTRINSICS["image_size"],
        CAMERA_ID,
    )
    (tmp_path / "atlas.json").write_text(marker_atlas().model_dump_json())
    return tmp_path


def test_the_table_puts_smeared_frames_in_the_wide_bands(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(
        [
            str(workspace / "atlas.json"),
            str(workspace / "walk.avi"),
            "--camera-id", CAMERA_ID,
            "--intrinsics", str(workspace / "intrinsics"),
            "--rig", str(REPOSITORY / "calib" / "rig.yaml"),
            "--step", "1",
            "--samples", "20",
        ]
    )  # fmt: skip

    printed = capsys.readouterr().out.splitlines()
    assert printed[0].startswith("8 frames with markers in 1 videos")
    bands = {line.split(" | ")[0]: line.split(" | ") for line in printed[2:-2]}
    assert sum(int(row[1]) for row in bands.values()) == 8
    assert "10+" in bands
    assert bands["10+"][-1] == "0 %"
    assert printed[-2].startswith("limit 5.5 px:")
    assert printed[-1].startswith("95 % region semi-major axis within the limit, quartiles:")
