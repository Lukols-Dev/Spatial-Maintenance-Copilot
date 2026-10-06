"""Export frames of a video, or a folder of photos, as PNG with the pixels the calibration reads.

Video frames come out in the orientation the video plays, as calibrate_camera.py
reads them; photos come out in the sensor grid, with their EXIF orientation
ignored. Either way, a pixel clicked on these PNGs is a pixel the intrinsics of
that capture mode describe, provided the calibration used the same kind of
source. A browser or an image viewer would rotate a JPEG by its EXIF tag and
shift every click; a PNG carries no such tag.
"""

import argparse
from pathlib import Path

import cv2 as cv
from smc_core.images import read_images
from smc_core.video import read_video_frames, sharpest_per_window


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="video of the scene, or a folder of photos")
    parser.add_argument("--out", type=Path, required=True, help="folder for the PNG files")
    parser.add_argument(
        "--window",
        type=int,
        default=15,
        help="video only: keep the sharpest frame of every n consecutive frames",
    )
    args = parser.parse_args(argv)

    if args.source.is_dir():
        frames = read_images(args.source)
    else:
        frames = sharpest_per_window(read_video_frames(args.source), args.window)

    args.out.mkdir(parents=True, exist_ok=True)
    count = 0
    for label, frame in frames:
        cv.imwrite(str(args.out / f"{Path(label).stem}.png"), frame)
        count += 1

    if count == 0:
        raise SystemExit(f"no frames found in {args.source}")
    print(f"wrote {count} PNG files to {args.out}")


if __name__ == "__main__":
    main()
