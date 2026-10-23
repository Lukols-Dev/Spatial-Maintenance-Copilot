"""The recordings the Localise page offers a judge: demo clips as H.264 MP4, and their index.

A judge has neither the asset nor its calibrated phone, so the page offers clips
of the phone instead: it plays one and sends its frames to the service, which
localises them as it would the live camera's. The page draws a clip's frames to
a canvas, and a browser allows that only for a video of the page's own origin,
so the clips are served beside the site (the site bucket's recordings/, see
infra/), uploaded from data/recordings/ at deploy and never kept in git.

The phone records HEVC, which not every browser plays, so each clip becomes
H.264, by ffmpeg where it is installed and by macOS's avconvert otherwise. The
picture keeps its size and turns upright, so its pixels stay those of the
calibrated capture mode; the conversion is refused if they do not. On demo_2 of
2026-10-23 the MP4 gave the same decision as the original at all 48 steps.

    uv run tools/judge_recordings.py \\
        "data/cabinet-aruco/2026-10-23/demo/demo_1.MOV=From the left side" \\
        "data/cabinet-aruco/2026-10-23/demo/demo_2.MOV=Too close" --out data/recordings
"""

import argparse
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import cv2 as cv

INDEX = "index.json"
# The size a frame must keep: the calibrated capture mode's, upright.
SIZE = (1080, 1920)

Convert = Callable[[Path, Path], None]


def ffmpeg(source: Path, target: Path) -> None:
    """H.264 at a quality that keeps the markers' edges, upright, without sound, ready to stream."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-an",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(target),
        ],
        check=True,
    )  # fmt: skip


def avconvert(source: Path, target: Path) -> None:
    """macOS's own converter: its 1080p preset is H.264, and it writes the picture upright."""
    subprocess.run(
        [
            "avconvert", "--source", str(source), "--output", str(target),
            "--preset", "Preset1920x1080", "--multiPass", "--replace",
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip


def converter() -> Convert:
    if shutil.which("ffmpeg"):
        return ffmpeg
    if shutil.which("avconvert"):
        return avconvert
    raise SystemExit("neither ffmpeg nor avconvert is installed: brew install ffmpeg")


def probe(path: Path) -> dict[str, object]:
    """The clip as a browser will play it: its codec, its upright size and its length."""
    capture = cv.VideoCapture(str(path), cv.CAP_FFMPEG)
    try:
        code = int(capture.get(cv.CAP_PROP_FOURCC))
        frames = int(capture.get(cv.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv.CAP_PROP_FPS) or 30.0
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise ValueError(f"{path.name} cannot be read")
    height, width = frame.shape[:2]
    return {
        "codec": "".join(chr((code >> 8 * index) & 0xFF) for index in range(4)).strip("\x00"),
        "width": width,
        "height": height,
        "seconds": round(frames / fps, 1),
    }


def clip_title(text: str) -> tuple[Path, str]:
    path, separator, title = text.partition("=")
    if not separator or not path or not title.strip():
        raise argparse.ArgumentTypeError(f"{text!r}: expected CLIP=TITLE")
    return Path(path), title.strip()


def build(clips: list[tuple[Path, str]], out: Path, convert: Convert) -> list[dict[str, object]]:
    """Every clip converted into out, checked, and listed in out's index.json in the order given."""
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for source, title in clips:
        target = out / f"{source.stem}.mp4"
        convert(source, target)
        found = probe(target)
        if found["codec"] not in {"avc1", "h264"}:
            raise ValueError(f"{target.name} came out as {found['codec']}, not H.264")
        if (found["width"], found["height"]) != SIZE:
            raise ValueError(
                f"{target.name} is {found['width']}x{found['height']} px, the camera's "
                f"frames are {SIZE[0]}x{SIZE[1]}"
            )
        entries.append({"file": target.name, "title": title, "seconds": found["seconds"]})
    index = {"recordings": entries}
    (out / INDEX).write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return entries


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("clips", type=clip_title, nargs="+", help="CLIP=TITLE, in the page's order")
    parser.add_argument("--out", type=Path, required=True, help="the folder the deploy uploads")
    args = parser.parse_args(argv)
    try:
        entries = build(args.clips, args.out, converter())
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
    for entry in entries:
        print(f"  {entry['file']}: {entry['seconds']} s, {entry['title']}")
    print(f"wrote {len(entries)} recordings and {INDEX} to {args.out}")


if __name__ == "__main__":
    main()
