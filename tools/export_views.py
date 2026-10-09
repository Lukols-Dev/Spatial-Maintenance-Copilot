"""Export frames of videos, or folders of photos, as PNG with the pixels the calibration reads.

Video frames come out in the orientation the video plays, as calibrate_camera.py
reads them; photos come out in the sensor grid, with their EXIF orientation
ignored. Either way, a pixel clicked on these PNGs is a pixel the intrinsics of
that capture mode describe, provided the calibration used the same kind of
source. A browser or an image viewer would rotate a JPEG by its EXIF tag and
shift every click; a PNG carries no such tag.

One video gives frame_000120.png and so on. Several videos share the folder, so
each name starts with its video's: close.MOV gives close_frame_000120.png. With
--one-per-video only the sharpest frame of each video is kept, named after the
video: B1_close.MOV gives B1_close.png. Photos keep their names.

--board keeps only the frames in which that board of the rig file shows the
corners a pose needs: the atlas build can use no other frame.
"""

import argparse
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import cv2 as cv
import numpy as np
from smc_core.board_pose import board_in_view
from smc_core.calibration import create_board
from smc_core.images import read_images
from smc_core.rig import load_rig_board
from smc_core.video import read_video_frames, sharpest_per_window

RIG_FILE = Path(__file__).resolve().parents[1] / "calib" / "rig.yaml"

Keep = Callable[[np.ndarray], bool]


def video_frames(
    video: Path, window: int, one_per_video: bool, prefixed: bool, keep: Keep | None
) -> Iterator[tuple[str, np.ndarray]]:
    """(PNG file name, frame) of the frames of one video to export."""
    frames = read_video_frames(video)
    if one_per_video:
        for _, frame in sharpest_per_window(frames, sys.maxsize, keep):
            yield f"{video.stem}.png", frame
        return
    prefix = f"{video.stem}_" if prefixed else ""
    for label, frame in sharpest_per_window(frames, window, keep):
        yield f"{prefix}{label}.png", frame


def photo_frames(folder: Path, keep: Keep | None) -> Iterator[tuple[str, np.ndarray]]:
    """(PNG file name, frame) of the photos of one folder to export."""
    for label, frame in read_images(folder):
        if keep is None or keep(frame):
            yield f"{Path(label).stem}.png", frame


def board_test(rig: Path, key: str) -> Keep:
    """Whether a frame shows the board `key` of the rig file well enough to pose on it."""
    measured = load_rig_board(rig, key)
    board = create_board(
        measured["squares_x"],
        measured["squares_y"],
        measured["square_mm"],
        measured["marker_mm"],
        measured["dictionary_id"],
        measured["marker_ids"],
    )
    detector = cv.aruco.CharucoDetector(board)
    return lambda frame: board_in_view(detector, board, frame)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "sources", type=Path, nargs="+", help="videos of the scene, or folders of photos"
    )
    parser.add_argument("--out", type=Path, required=True, help="folder for the PNG files")
    parser.add_argument(
        "--window",
        type=int,
        default=15,
        help="video only: keep the sharpest frame of every n consecutive frames",
    )
    parser.add_argument(
        "--one-per-video",
        action="store_true",
        help="keep only the sharpest frame of each video, named after the video",
    )
    parser.add_argument(
        "--board", help="keep only frames that show this board of the rig file, e.g. rig_board_b"
    )
    parser.add_argument("--rig", type=Path, default=RIG_FILE, help="measured boards")
    args = parser.parse_args(argv)

    videos = [source for source in args.sources if not source.is_dir()]
    stems = [video.stem for video in videos]
    shared = sorted({stem for stem in stems if stems.count(stem) > 1})
    if shared:
        raise SystemExit(f"videos with the same name would overwrite each other: {shared}")

    keep = None
    if args.board is not None:
        try:
            keep = board_test(args.rig, args.board)
        except ValueError as error:
            raise SystemExit(str(error)) from error

    args.out.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    for source in args.sources:
        if source.is_dir():
            frames = photo_frames(source, keep)
        else:
            frames = video_frames(source, args.window, args.one_per_video, len(videos) > 1, keep)
        count = 0
        for name, frame in frames:
            if name in written:
                raise SystemExit(f"{name} would be written twice; rename one of the sources")
            cv.imwrite(str(args.out / name), frame)
            written.add(name)
            count += 1
        print(f"{source}: {count} PNG files")

    if not written:
        raise SystemExit(f"no frames found in {', '.join(map(str, args.sources))}")
    print(f"wrote {len(written)} PNG files to {args.out}")


if __name__ == "__main__":
    main()
