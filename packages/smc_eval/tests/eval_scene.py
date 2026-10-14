"""A frozen dataset of the synthetic scene: every answer of the evaluation is known.

The test set, "cabinet-b", has four viewpoints with the target hidden:

- A_close sees every landmark from viewpoint 2: the policy accepts it.
  A_open is the shot from the same spot with the target in sight, its truth.
- B_close sees four landmarks from viewpoint 6: too few inliers, the policy asks
  to move closer, and A is the viewpoint that way. B_open is its truth.
- C_close sees three landmarks from viewpoint 0: no pose. C_open is its truth.
- D_close sees every landmark from viewpoint 7 and has no truth.

The build set, "cabinet-atlas", is viewpoints 3 to 5 with every point clicked,
as the views an atlas is built from. In memory, the board poses are the true
camera poses.

write_workspace puts the same scene on disk, as the tools find a workspace:
the frames rendered, the camera calibrated, the rig board measured, the atlas
built, and a video.
"""

import json
from pathlib import Path

import cv2 as cv
from smc_core.calibration import save_calibration
from smc_core.contracts import Clicks, Pose, Vec2
from smc_core.testing import (
    CAMERA_ID,
    INTRINSICS,
    POINTS_MM,
    TARGET_ID,
    VIEWPOINTS,
    calibration,
    camera_pose,
    clicks_for,
    render,
    rig_board,
    scene_atlas,
)
from smc_eval.dataset import BoardPose, Dataset, ViewSet
from smc_eval.results import Environment

TEST, BUILD = "cabinet-b", "cabinet-atlas"
ACCEPTED, MOVES, BLIND, UNSCORED = "A_close.png", "B_close.png", "C_close.png", "D_close.png"
LANDMARKS = [point for point in POINTS_MM if point != TARGET_ID]
EVERY_POINT = [*LANDMARKS, TARGET_ID]
CLICK_ERROR_PX = 0.5
# Few samples: the measures are checked for what they count, not for their precision.
SAMPLES = 100
ENVIRONMENT = Environment(
    git_commit="abc123",
    git_dirty=False,
    python="3.14",
    numpy="2",
    opencv="5",
    langgraph="1",
    machine="test",
)

# Each frame of the two sets, by the viewpoint it is taken from.
TEST_FRAMES = {
    ACCEPTED: 2,
    "A_open.png": 2,
    MOVES: 6,
    "B_open.png": 6,
    BLIND: 0,
    "C_open.png": 0,
    UNSCORED: 7,
}
BUILD_FRAMES = {f"frame_{index}.png": index for index in (3, 4, 5)}


def clicked(index: int, points: list[str]) -> dict[str, Vec2]:
    every = clicks_for(CLICK_ERROR_PX).views[f"view_{index}.png"]
    return {point: every[point] for point in points}


def held_out_clicks() -> Clicks:
    return Clicks(
        camera_id=CAMERA_ID,
        views={
            ACCEPTED: clicked(2, LANDMARKS),
            "A_open.png": clicked(2, EVERY_POINT),
            MOVES: clicked(6, LANDMARKS[:4]),
            "B_open.png": clicked(6, EVERY_POINT),
            BLIND: clicked(0, LANDMARKS[:3]),
            "C_open.png": clicked(0, EVERY_POINT),
            UNSCORED: clicked(7, LANDMARKS),
        },
    )


def build_clicks() -> Clicks:
    return Clicks(
        camera_id=CAMERA_ID,
        views={name: clicked(index, EVERY_POINT) for name, index in BUILD_FRAMES.items()},
    )


def true_pose(index: int) -> BoardPose:
    rotation, tvec = camera_pose(*VIEWPOINTS[index])
    rvec, _ = cv.Rodrigues(rotation)
    return BoardPose(
        pose=Pose(
            rvec=(float(rvec[0, 0]), float(rvec[1, 0]), float(rvec[2, 0])),
            tvec_mm=(float(tvec[0]), float(tvec[1]), float(tvec[2])),
        ),
        corners=24,
        rms_px=0.1,
    )


def scene_dataset() -> Dataset:
    return Dataset(
        name="synthetic",
        manifest_sha256="0" * 64,
        atlas=scene_atlas(),
        intrinsics=INTRINSICS,
        sigma_px=1.0,
        sets={
            TEST: ViewSet(
                TEST, "test", held_out_clicks(), {ACCEPTED: true_pose(2), MOVES: true_pose(6)}
            ),
            BUILD: ViewSet(
                BUILD,
                "build",
                build_clicks(),
                {name: true_pose(index) for name, index in BUILD_FRAMES.items()},
            ),
        },
    )


# ---- on disk ---------------------------------------------------------------------------

# rig_board_a is the board of smc_core.testing, measured.
RIG_YAML = """\
dictionary: DICT_5X5_100
marker_ratio: 0.72
boards:
  rig_board_a:
    squares_x: 4
    squares_y: 6
    ids: [20, 31]
    square_nominal_mm: 25.0
    marker_nominal_mm: 18.0
    square_measured_mm: 25.0
    marker_measured_mm: 18.0
    measurement_uncertainty_mm: 0.1
    substrate: paperboard
    measured_on: 2026-10-09
"""


def write_frames(folder: Path, frames: dict[str, int], clicks: Clicks) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    board = rig_board()
    for name, index in frames.items():
        assert cv.imwrite(str(folder / name), render(board, *camera_pose(*VIEWPOINTS[index])))
    (folder / "clicks.json").write_text(clicks.model_dump_json(indent=2) + "\n")
    return folder


def write_workspace(root: Path) -> dict[str, Path]:
    """The scene as files in root: what freeze_dataset.py is pointed at."""
    camera = root / "calib" / "intrinsics" / "phone.yml"
    camera.parent.mkdir(parents=True)
    save_calibration(str(camera), calibration(), INTRINSICS["image_size"], CAMERA_ID)
    (root / "calib" / "rig.yaml").write_text(RIG_YAML)

    atlas = root / "data" / "atlas" / "home-cabinet.json"
    atlas.parent.mkdir(parents=True)
    atlas.write_text(scene_atlas().model_dump_json(indent=2) + "\n")
    report = {"built_at": "2026-10-09T12:00:00+02:00", "request": {"click_sigma_px": 1.0}}
    atlas.with_name("home-cabinet.report.json").write_text(json.dumps(report))

    videos = root / "data" / "recordings"
    (videos / "B").mkdir(parents=True)
    (videos / "B" / "B1_close.MOV").write_bytes(b"not really a video")
    (videos / "notes.txt").write_text("not a video at all")
    return {
        "atlas": atlas,
        "camera": camera,
        "test": write_frames(root / "data" / "views" / TEST, TEST_FRAMES, held_out_clicks()),
        "build": write_frames(root / "data" / "views" / BUILD, BUILD_FRAMES, build_clicks()),
        "videos": videos,
    }
