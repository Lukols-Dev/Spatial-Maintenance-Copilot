"""The evidence for the blur limit: how far a frame's target jumps against how smeared its markers are.

A frame taken while the camera moves localises with a small reprojection error
and a pose that is off all the same, which no check of the fit sees
(smc_core.blur). This localises every n-th frame of videos of the asset against
its atlas, as the Guide page does, and measures the target's jitter: how far
its projection lies from the mean of the frames before and after it. A smooth
path of the camera cancels out of that mean; the pose's own error does not.

For each band of marker edge width the table gives the frames, their RMS
reprojection, the jitter's median and 90th percentile, and the share the policy
accepts without the blur check and with it, then the quartiles of the 95%
region's size. Policy.max_edge_width_px is set where the jitter's 90th
percentile leaves the 95% region of a typical frame.

    uv run tools/blur_limit.py data/atlas/cabinet-aruco.json \\
        data/cabinet-aruco/demo/demo_1.MOV data/cabinet-aruco/demo/demo_2.MOV \\
        --camera-id iphone11-1x-1080p-portrait
"""

import argparse
import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np
from smc_core.calibration import Intrinsics, load_calibration
from smc_core.contracts import Vec2, load_atlas
from smc_core.frames import localise_frame
from smc_core.markers import load_marker_set, marker_detector
from smc_core.policy import DEFAULT_POLICY, decide
from smc_core.video import read_video_frames

ROOT = Path(__file__).resolve().parents[1]
BANDS = (3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 10.0)


@dataclass(frozen=True)
class Sample:
    """One localised frame with markers to measure."""

    edge_width_px: float
    rms_px: float | None
    target_px: Vec2 | None
    semi_major_px: float | None
    accepted_without_blur: bool
    accepted: bool


def jitter(targets: Sequence[Vec2 | None]) -> list[float | None]:
    """Each target's distance from the mean of its neighbours; None at the ends or beside a gap."""
    jumps: list[float | None] = [None] * len(targets)
    for index in range(1, len(targets) - 1):
        before, here, after = targets[index - 1], targets[index], targets[index + 1]
        if before is None or here is None or after is None:
            continue
        jumps[index] = math.hypot(
            here[0] - (before[0] + after[0]) / 2, here[1] - (before[1] + after[1]) / 2
        )
    return jumps


def intrinsics_of(folder: Path, camera_id: str) -> Intrinsics:
    for path in sorted(folder.glob("*.yml")):
        intrinsics = load_calibration(str(path))
        if intrinsics["camera_id"] == camera_id:
            return intrinsics
    raise SystemExit(f"no intrinsics for {camera_id} in {folder}")


def bands_table(rows: list[tuple[Sample, float | None]], edges: Sequence[float]) -> list[str]:
    """The table, one line per band of edge width that has frames."""
    lines = [
        "edge width px | frames | RMS px median | jitter px median | jitter px p90 "
        "| accepted without blur check | accepted"
    ]
    limits = [0.0, *edges, math.inf]
    for low, high in pairwise(limits):
        band = [(sample, jump) for sample, jump in rows if low <= sample.edge_width_px < high]
        if not band:
            continue
        rms = [sample.rms_px for sample, _ in band if sample.rms_px is not None]
        jumps = [jump for _, jump in band if jump is not None]
        name = f"{low:g}-{high:g}" if math.isfinite(high) else f"{low:g}+"
        lines.append(
            f"{name} | {len(band)} | {_median(rms)} | {_median(jumps)} | {_p90(jumps)} "
            f"| {_share(sum(s.accepted_without_blur for s, _ in band), len(band))} "
            f"| {_share(sum(s.accepted for s, _ in band), len(band))}"
        )
    return lines


def _median(values: list[float]) -> str:
    return f"{float(np.median(values)):.2f}" if values else "-"


def _p90(values: list[float]) -> str:
    return f"{float(np.percentile(values, 90)):.2f}" if values else "-"


def _share(count: int, total: int) -> str:
    return f"{100 * count / total:.0f} %"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("atlas", type=Path, help="the atlas file (.json), built from markers")
    parser.add_argument("videos", type=Path, nargs="+", help="videos of the asset")
    parser.add_argument("--camera-id", required=True, help="the camera the videos were taken with")
    parser.add_argument("--intrinsics", type=Path, default=ROOT / "calib" / "intrinsics")
    parser.add_argument("--rig", type=Path, default=ROOT / "calib" / "rig.yaml")
    parser.add_argument("--step", type=int, default=2, help="every n-th frame of a video")
    parser.add_argument("--samples", type=int, default=30, help="Monte Carlo samples per frame")
    parser.add_argument("--sigma-px", type=float, default=1.0, help="a marker corner's error")
    args = parser.parse_args(argv)

    atlas = load_atlas(args.atlas)
    intrinsics = intrinsics_of(args.intrinsics, args.camera_id)
    markers = load_marker_set(args.rig)
    detector = marker_detector(markers)

    rows: list[tuple[Sample, float | None]] = []
    for video in args.videos:
        samples: list[Sample | None] = []
        for label, frame in read_video_frames(video, step=args.step):
            result = localise_frame(
                frame, label, atlas, intrinsics, detector, markers, args.sigma_px, args.samples
            )
            width = result.quality.edge_width_px
            if width is None:
                samples.append(None)
                continue
            quality, target = result.localisation.quality, result.localisation.target
            region = result.localisation.uncertainty
            plain = decide(result.localisation, result.view, atlas, intrinsics)
            samples.append(
                Sample(
                    edge_width_px=width,
                    rms_px=None if quality is None else quality.rms_reprojection_px,
                    target_px=None if target is None else target.centre_px,
                    semi_major_px=None if region is None else region.ellipse.semi_major_px,
                    accepted_without_blur=plain.reliable,
                    accepted=result.decision.reliable,
                )
            )
        jumps = jitter([None if sample is None else sample.target_px for sample in samples])
        rows += [(sample, jump) for sample, jump in zip(samples, jumps, strict=True) if sample]

    if not rows:
        raise SystemExit("no frame with a marker of the rig in the videos")
    limit = DEFAULT_POLICY.max_edge_width_px
    above = sum(sample.edge_width_px > limit for sample, _ in rows)
    print(f"{len(rows)} frames with markers in {len(args.videos)} videos, every {args.step}")
    for line in bands_table(rows, BANDS):
        print(line)
    print(f"limit {limit:g} px: {above} of {len(rows)} frames held still")
    regions = [
        sample.semi_major_px
        for sample, _ in rows
        if sample.semi_major_px is not None and sample.edge_width_px <= limit
    ]
    if regions:
        quartiles = ", ".join(f"{value:.1f}" for value in np.percentile(regions, [25, 50, 75]))
        print(f"95 % region semi-major axis within the limit, quartiles: {quartiles} px")


if __name__ == "__main__":
    main()
