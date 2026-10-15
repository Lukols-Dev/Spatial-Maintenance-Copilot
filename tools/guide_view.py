"""Give an atlas its guide view: the recorded pose its target is best localised from.

The view set's frames are posed by the rig board that defines the atlas's
frame, as the atlas builder poses them. The pose that saw the most landmarks
of the atlas, with the target nearest the middle among equals, becomes the
guide view, which guidance leads the camera to. Atlases built since the guide
view existed have one already; this gives one to an older atlas.

    uv run tools/guide_view.py data/atlas/szafka.json data/views/szafka-atlas
"""

import argparse
from pathlib import Path

import cv2 as cv
import numpy as np
from smc_core.atlas_build import board_pose
from smc_core.board_pose import pose_views
from smc_core.calibration import create_board, load_calibration
from smc_core.contracts import load_atlas, load_clicks
from smc_core.guidance import choose_guide_view
from smc_core.images import read_images
from smc_core.rig import load_rig_board

ROOT = Path(__file__).resolve().parents[1]


def intrinsics_file(folder: Path, camera_id: str) -> Path:
    for path in sorted(folder.glob("*.yml")):
        if load_calibration(str(path))["camera_id"] == camera_id:
            return path
    raise SystemExit(f"no intrinsics for {camera_id} in {folder}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("atlas", type=Path, help="the atlas file (.json)")
    parser.add_argument("views", type=Path, help="the view set the atlas was built from")
    parser.add_argument("--intrinsics", type=Path, default=ROOT / "calib" / "intrinsics")
    parser.add_argument("--rig", type=Path, default=ROOT / "calib" / "rig.yaml")
    parser.add_argument("--out", type=Path, help="where to write; default: the atlas file")
    args = parser.parse_args(argv)

    atlas = load_atlas(args.atlas)
    board_key = atlas.frame.removeprefix("board:")
    if board_key == atlas.frame:
        raise SystemExit(f"the atlas frame {atlas.frame!r} is not a rig board's")
    clicks = load_clicks(args.views / "clicks.json")
    intrinsics = load_calibration(str(intrinsics_file(args.intrinsics, clicks.camera_id)))
    try:
        rig = load_rig_board(args.rig, board_key)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    board = create_board(
        rig["squares_x"],
        rig["squares_y"],
        rig["square_mm"],
        rig["marker_mm"],
        rig["dictionary_id"],
        rig["marker_ids"],
    )
    posed = pose_views(
        read_images(args.views),
        cv.aruco.CharucoDetector(board),
        board,
        intrinsics,
        np.random.default_rng(0),
        samples=0,
    )
    poses = {name: board_pose(pose) for name, pose in posed.items()}
    guide = choose_guide_view(poses, clicks, atlas, intrinsics)
    if guide is None:
        raise SystemExit(f"no frame of {args.views} shows the board with the target in frame")
    chosen = next(name for name, pose in poses.items() if pose == guide)

    out = args.out or args.atlas
    written = atlas.model_copy(update={"guide_view": guide})
    out.write_text(written.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"{out}: guide view from {chosen}, one of {len(poses)} posed frames")


if __name__ == "__main__":
    main()
