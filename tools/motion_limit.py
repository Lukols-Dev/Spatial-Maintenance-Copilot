"""The evidence for the Guide's motion thresholds: a small grey picture's change against the markers' motion.

The Guide page tells a live camera's motion from the camera's own picture
(apps/web/lib/guide/motion.ts): each frame drawn 160 px on its longer side, in
grey, and its change from the frame before, the mean absolute difference of the
two less their mean brightness. This measures the same on videos of the asset,
frame by frame, and holds it against how far the printed markers moved between
the two frames, the median of their corners' mean displacement in full-size
pixels.

It prints the rank correlation of the two, the share of the pairs with the
markers under TREMOR_PX below STILL_BELOW, of those at MOVE_PX or more above
MOVING_ABOVE, and the change's spread in bands of marker motion. Videos of the
Camera app are steadied; a browser's live camera is not, which is why the
steady threshold takes in a hand's tremor of a few pixels a frame.

    uv run tools/motion_limit.py data/szafka2_demo/demo_1.MOV data/szafka2_demo/demo_2.MOV
"""

import argparse
from itertools import pairwise
from pathlib import Path

import cv2 as cv
import numpy as np
from smc_core.markers import load_marker_set, marker_detector
from smc_core.video import read_video_frames

ROOT = Path(__file__).resolve().parents[1]
# As apps/web/lib/guide/motion.ts has them.
SAMPLE_LONG_SIDE = 160
STILL_BELOW = 2.5
MOVING_ABOVE = 3.5
# The markers' motion, in px a frame, the thresholds tell apart: a hand's tremor, a move.
TREMOR_PX = 4.0
MOVE_PX = 8.0
BANDS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)


def sample(frame: np.ndarray) -> np.ndarray:
    """The frame small and grey, as the page draws it: its longer side SAMPLE_LONG_SIDE, averaged down."""
    height, width = frame.shape[:2]
    scale = SAMPLE_LONG_SIDE / max(width, height)
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    grey = cv.cvtColor(frame, cv.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return cv.resize(grey, size, interpolation=cv.INTER_AREA).astype(np.float32)


def picture_change(a: np.ndarray, b: np.ndarray) -> float:
    """The mean absolute difference of two pictures, each less its mean brightness."""
    return float(np.mean(np.abs((b - b.mean()) - (a - a.mean()))))


def rank_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman's rho, as the correlation of the ranks."""
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("videos", type=Path, nargs="+", help="videos of the asset with its markers")
    parser.add_argument("--rig", type=Path, default=ROOT / "calib" / "rig.yaml")
    args = parser.parse_args(argv)

    detector = marker_detector(load_marker_set(args.rig))
    changes: list[float] = []
    moved: list[float] = []
    for video in args.videos:
        before: tuple[np.ndarray, dict[int, np.ndarray]] | None = None
        for _, frame in read_video_frames(video):
            corners, ids, _ = detector.detectMarkers(cv.cvtColor(frame, cv.COLOR_BGR2GRAY))
            found = (
                {}
                if ids is None
                else {int(i): q.reshape(4, 2) for i, q in zip(ids.ravel(), corners, strict=True)}
            )
            now = (sample(frame), found)
            if before is not None:
                common = sorted(set(before[1]) & set(found))
                if common:
                    shifts = [
                        np.linalg.norm(found[i] - before[1][i], axis=1).mean() for i in common
                    ]
                    changes.append(picture_change(before[0], now[0]))
                    moved.append(float(np.median(shifts)))
            before = now

    if not changes:
        raise SystemExit("no pair of frames with a marker of the rig in both")
    change, motion = np.array(changes), np.array(moved)
    tremor, moving = motion < TREMOR_PX, motion >= MOVE_PX
    print(f"{len(change)} pairs of consecutive frames with markers in {len(args.videos)} videos")
    print(f"rank correlation with the markers' motion: {rank_correlation(change, motion):.2f}")
    if tremor.any():
        share = np.mean(change[tremor] < STILL_BELOW)
        print(
            f"markers under {TREMOR_PX:g} px: {tremor.sum()} pairs, {share:.0%} below {STILL_BELOW:g}"
        )
    if moving.any():
        share = np.mean(change[moving] > MOVING_ABOVE)
        print(
            f"markers {MOVE_PX:g} px or more: {moving.sum()} pairs, {share:.0%} above {MOVING_ABOVE:g}"
        )
    print("markers px | pairs | change p10 | median | p90")
    for low, high in pairwise((0.0, *BANDS, np.inf)):
        band = change[(motion >= low) & (motion < high)]
        if len(band):
            name = f"{low:g}-{high:g}" if np.isfinite(high) else f"{low:g}+"
            p10, p50, p90 = np.percentile(band, [10, 50, 90])
            print(f"{name} | {len(band)} | {p10:.2f} | {p50:.2f} | {p90:.2f}")


if __name__ == "__main__":
    main()
