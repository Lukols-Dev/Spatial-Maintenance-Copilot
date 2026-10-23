"""Export the frames of viewpoint clips: a spot filmed from a tripod, the target hidden, then in sight.

One clip a spot, the camera never touched: the panel shut for a few seconds,
someone opening it, the panel open for a few seconds, and shut again for a few
more. The still stretch before the opening gives the viewpoint and the one after
it the truth, both from one camera pose, which two clips cannot promise: on
2026-10-15 the camera moved up to 94 mm between the two clips of a spot. The
stretch after the panel is shut again is a repeat of the viewpoint from the same
camera, with the panel closed once more.

A stretch is still while the picture barely changes from frame to frame,
measured as the Guide page measures a live camera's motion
(tools/motion_limit.py): a person walking past changes it far more than a
camera on a tripod ever does, and the limit follows the clip's own still
frames, since from two metres away the person is small. The first stretch is the shut panel; the open one
is the last stretch that shows the tag, so a clip may end with the panel shut
again. From each the frame with the most marker corners, the sharpest of those,
is kept. T01.MOV gives T01_close.png, T01_open.png and, shut again,
T01_2_close.png: the evaluation reads two shots of one spot as a repeat. A clip
named with a take, T01_1.MOV, is one more shot of the shut panel recorded
apart; it gives T01_1_close.png only if its camera stands where the spot's did,
since the spot's open frame is its truth too. A tap on the phone to stop and
start moved the take of 2026-10-23 by 7.7 px, so a take is checked against its
spot and left out when it moved.

Every clip is checked, and the checks are printed:

- the shut frame shows no tag, and a still stretch follows the opening;
- the open frame shows the tag; without it the spot has no truth, and no open
  frame is written;
- the markers off the panel (those not in --moving) stand still from the shut
  frame to the open one, and to the shut-again one: a camera that moved shows
  here, in pixels.

    uv run tools/viewpoint_clips.py data/cabinet-aruco/2026-10-23/tripod/*.MOV \\
        --out data/views/cabinet-aruco-tripod --moving 50 51 52 53
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2 as cv
import numpy as np
from motion_limit import STILL_BELOW, picture_change, sample
from smc_core.blur import frame_quality
from smc_core.markers import Detection, MarkerSet, detect, load_marker_set, marker_detector
from smc_core.video import read_video_frames

RIG_FILE = Path(__file__).resolve().parents[1] / "calib" / "rig.yaml"
# Left out at both ends of a still stretch, in seconds: the picture settling
# after a tap on the screen, or after a person left the frame.
SETTLE_S = 0.5
# The shortest still stretch that counts once the settling is left out, in seconds.
SHORTEST_S = 0.5
# Every n-th frame of a stretch is searched for markers; neighbours are alike.
SEARCH_STEP = 3
# A still camera's marker corners agree to a tenth of a pixel between frames;
# beyond this the camera moved between the shut frame and the open one.
MOVED_PX = 1.0
# A panel's marker counts as moved with its panel once it shifts this far.
PANEL_MOVED_PX = 5.0
# A still camera's markers have edges about three pixels wide (smc_core.blur).
BLURRED_PX = 4.5
# A camera two metres away sees the person who opens the panel small: on T08 of
# 2026-10-23 the picture changed by 2.0 at most while it was opened, under the
# Guide's limit for a moving hand-held camera. A clip's own still frames change
# by about 0.5, so the limit follows them: twice their median, at least 0.9.
NOISE_FACTOR = 2.0
LOWEST_LIMIT = 0.9


@dataclass(frozen=True)
class Pick:
    """The frame kept from a still stretch: where it is in the clip, and the markers in it."""

    index: int
    frame: np.ndarray
    detection: Detection
    edge_width_px: float | None


@dataclass
class ClipCheck:
    """What one clip gave: its shut and open frames, the camera's shift between them, what is wrong."""

    name: str
    fps: float
    frames: int
    stretches: list[tuple[int, int]]
    shut: Pick | None = None
    opened: Pick | None = None
    reclosed: Pick | None = None  # shut again after the opening, the camera unmoved
    shift_px: float | None = None
    dropped: bool = False  # a take whose camera moved away from its spot's
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def has_truth(self) -> bool:
        return self.opened is not None and self.opened.detection.tag is not None


def is_take(name: str) -> bool:
    """T01_1 is one more shot of spot T01's shut panel; T01 is the spot's own clip."""
    return "_" in name


def marker_of(point_id: str) -> int | None:
    """The marker a landmark corner belongs to: m50_2 is a corner of 50; the target's points have none."""
    head, _, corner = point_id.partition("_")
    if not head.startswith("m") or not corner:
        return None
    return int(head[1:]) if head[1:].isdigit() else None


def still_stretches(
    changes: Sequence[float], settle: int, shortest: int, limit: float = STILL_BELOW
) -> list[tuple[int, int]]:
    """The still stretches of a clip as (first, last) frame, the settling left out at both ends.

    changes[i] is the picture's change from frame i - 1 to frame i; changes[0]
    is not read. A frame is still when the picture changes neither into it nor
    out of it.
    """
    count = len(changes)
    still = [
        (index == 0 or changes[index] <= limit)
        and (index + 1 == count or changes[index + 1] <= limit)
        for index in range(count)
    ]
    stretches: list[tuple[int, int]] = []
    start: int | None = None
    for index, is_still in enumerate([*still, False]):
        if is_still and start is None:
            start = index
        elif not is_still and start is not None:
            first, last = start + settle, index - 1 - settle
            if last - first + 1 >= shortest:
                stretches.append((first, last))
            start = None
    return stretches


def frame_rate(video: Path) -> float:
    """The clip's frames a second, as the file states it; 30 when it states none."""
    capture = cv.VideoCapture(video, cv.CAP_FFMPEG)
    try:
        fps = capture.get(cv.CAP_PROP_FPS)
    finally:
        capture.release()
    return fps if fps > 0 else 30.0


def picture_changes(video: Path) -> list[float]:
    """The picture's change into every frame of the clip; 0 for the first."""
    changes: list[float] = []
    previous: np.ndarray | None = None
    for _, frame in read_video_frames(video):
        small = sample(frame)
        changes.append(0.0 if previous is None else picture_change(previous, small))
        previous = small
    return changes


def _corners(detection: Detection, markers: set[int]) -> dict[str, tuple[float, float]]:
    return {
        point: pixel for point, pixel in detection.landmarks.items() if marker_of(point) in markers
    }


def _score(pick: Pick, fixed: set[int], opened: bool) -> tuple[int, int, float]:
    """The better frame of a stretch: the tag in sight when open, more corners, then narrower edges."""
    tag = int(pick.detection.tag is not None) if opened else 0
    corners = len(_corners(pick.detection, fixed)) if opened else len(pick.detection.landmarks)
    width = pick.edge_width_px if pick.edge_width_px is not None else float("inf")
    return tag, corners, -width


def pick_frames(
    video: Path,
    stretches: Sequence[tuple[int, int]],
    detector: cv.aruco.ArucoDetector,
    markers: MarkerSet,
    fixed: set[int],
    opened: Sequence[bool],
) -> list[Pick | None]:
    """The best frame of each stretch, in one pass over the clip; None for a stretch with no marker."""
    best: list[Pick | None] = [None] * len(stretches)
    last = max((end for _, end in stretches), default=-1)
    for index, (_, frame) in enumerate(read_video_frames(video)):
        if index > last:
            break
        for which, (first, end) in enumerate(stretches):
            if not first <= index <= end or (index - first) % SEARCH_STEP:
                continue
            # Every marker counts here: which belong to the panel is for the checks to say.
            detection = detect(detector, markers, frame)
            if not detection.landmarks and detection.tag is None:
                continue
            quality = frame_quality(frame, detection.quads)
            pick = Pick(index, frame, detection, quality.edge_width_px)
            current = best[which]
            if current is None or _score(pick, fixed, opened[which]) > _score(
                current, fixed, opened[which]
            ):
                best[which] = pick
    return best


def camera_shift(shut: Detection, opened: Detection, fixed: set[int]) -> float | None:
    """How far the corners of the markers off the panel moved from the shut frame to the open one: the median, px."""
    before, after = _corners(shut, fixed), _corners(opened, fixed)
    shared = sorted(before.keys() & after.keys())
    if not shared:
        return None
    return float(np.median([np.hypot(*np.subtract(after[key], before[key])) for key in shared]))


def panel_moved(shut: Detection, opened: Detection, moving: set[int]) -> bool | None:
    """Whether the panel's markers left the places they had while it was shut; None when none was in sight."""
    before, after = _corners(shut, moving), _corners(opened, moving)
    if not before:
        return None
    return any(
        key not in after or np.hypot(*np.subtract(after[key], before[key])) >= PANEL_MOVED_PX
        for key in before
    )


def shut_shift(
    first: Detection, second: Detection, fixed: set[int], everyone: set[int]
) -> float | None:
    """How far the camera moved between two frames of the shut panel: on the markers off the panel, else on all."""
    shift = camera_shift(first, second, fixed)
    return shift if shift is not None else camera_shift(first, second, everyone)


def check_clip(
    video: Path, detector: cv.aruco.ArucoDetector, markers: MarkerSet, moving: set[int]
) -> ClipCheck:
    """The shut and open frames of one clip, and every check on them."""
    name = video.stem
    fps = frame_rate(video)
    changes = picture_changes(video)
    noise = float(np.median(changes[1:])) if len(changes) > 1 else 0.0
    limit = min(STILL_BELOW, max(LOWEST_LIMIT, NOISE_FACTOR * noise))
    stretches = still_stretches(
        changes, round(SETTLE_S * fps), max(1, round(SHORTEST_S * fps)), limit
    )
    check = ClipCheck(name=name, fps=fps, frames=len(changes), stretches=stretches)
    if not stretches:
        check.problems.append("no still stretch: the camera moved all through the clip")
        return check

    take = is_take(name)
    chosen = stretches[:1] if take else stretches
    fixed = set(markers.landmark_ids) - moving
    picks = pick_frames(
        video, chosen, detector, markers, fixed, [False] + [True] * (len(chosen) - 1)
    )
    check.shut = picks[0]
    # The open stretch is the last that shows the tag: a clip may end with the
    # panel shut again. Where the tag stays out of sight, the last stretch whose
    # panel markers left their places; with neither, the last stretch.
    later = [pick for pick in picks[1:] if pick is not None]
    showing = [pick for pick in later if pick.detection.tag is not None]
    opened = (
        [
            pick
            for pick in later
            if panel_moved(check.shut.detection, pick.detection, moving) is True
        ]
        if check.shut is not None
        else []
    )
    check.opened = (showing or opened or later or [None])[-1]
    after = [pick for pick in later if check.opened and pick.index > check.opened.index]

    if check.shut is None:
        check.problems.append("no marker in sight before the opening")
        return check
    if check.shut.detection.tag is not None:
        check.problems.append("the tag is in sight in the first still stretch: was the panel shut?")
    if take:
        if len(stretches) > 1:
            check.notes.append("the picture moved during the take; its first still stretch is used")
        return check

    if len(stretches) == 1:
        check.problems.append("no still stretch after the opening: was the panel opened?")
        return check
    if check.opened is None:
        check.problems.append("no marker in sight after the opening")
        return check

    check.shift_px = camera_shift(check.shut.detection, check.opened.detection, fixed)
    if check.shift_px is None:
        check.notes.append(
            "no marker off the panel in both frames: the camera's stillness is not checked"
        )
    elif check.shift_px > MOVED_PX:
        check.problems.append(
            f"the camera moved {check.shift_px:.1f} px between the shut and the open frame"
        )
    if check.opened.detection.tag is None:
        if panel_moved(check.shut.detection, check.opened.detection, moving) is False:
            check.problems.append("the panel's markers did not move: was the panel opened?")
        check.notes.append("the tag is not in sight with the panel open: no truth from this spot")
    for pick, which in ((check.shut, "shut"), (check.opened, "open")):
        if pick.edge_width_px is not None and pick.edge_width_px > BLURRED_PX:
            check.notes.append(f"the {which} frame is blurred: edges {pick.edge_width_px:.1f} px")
    # Shut again: of the still stretches after the opening that show the panel
    # back where it was, the one whose camera agrees best with the first; the
    # last is often the moment a finger reaches for the stop button. With no
    # marker off the panel in sight, the panel's own markers tell a still camera.
    shut_again = [
        pick
        for pick in after
        if pick.detection.tag is None
        and panel_moved(check.shut.detection, pick.detection, moving) is not True
    ]
    everyone = set(markers.landmark_ids)
    shifts = [
        (shift, pick)
        for pick in shut_again
        if (shift := shut_shift(check.shut.detection, pick.detection, fixed, everyone)) is not None
    ]
    if after and not shut_again:
        check.notes.append("the panel was not shut again after the opening: no repeat")
    elif shut_again and not shifts:
        check.notes.append("shut again, the camera cannot be checked: no repeat")
    elif shifts:
        shift, best = min(shifts, key=lambda item: item[0])
        if shift > MOVED_PX:
            check.notes.append(f"shut again, the camera moved {shift:.1f} px: no repeat")
        else:
            check.reclosed = best
            if check.shift_px is None:
                check.notes = [note for note in check.notes if not note.startswith("no marker off")]
                check.notes.append(
                    f"no marker off the panel when open; shut before and after, the camera "
                    f"agrees to {shift:.2f} px"
                )
    return check


def compare_takes(checks: Sequence[ClipCheck], fixed: set[int]) -> None:
    """Hold every take against its spot's shut frame, and leave out the takes whose camera moved."""
    spots = {check.name: check for check in checks if not is_take(check.name)}
    for take in (check for check in checks if is_take(check.name)):
        spot = spots.get(take.name.split("_", 1)[0])
        if spot is None or spot.shut is None or take.shut is None:
            take.notes.append("its spot's clip is not here: the take is not checked")
            continue
        take.shift_px = camera_shift(spot.shut.detection, take.shut.detection, fixed)
        if take.shift_px is None or take.shift_px > MOVED_PX:
            take.dropped = True
            moved = "cannot be checked" if take.shift_px is None else f"{take.shift_px:.1f} px"
            take.notes.append(
                f"left out: the camera moved from the spot's ({moved}), so its truth does not hold"
            )


def write_frames(check: ClipCheck, out: Path) -> list[str]:
    """The clip's frames as PNG files in out: the shut frame, and the open one when it shows the tag."""
    written = []
    if check.shut is not None and not check.dropped:
        written.append(f"{check.name}_close.png")
        cv.imwrite(str(out / written[-1]), check.shut.frame)
    if check.opened is not None and check.has_truth:
        written.append(f"{check.name}_open.png")
        cv.imwrite(str(out / written[-1]), check.opened.frame)
    if check.reclosed is not None:
        written.append(f"{check.name}_2_close.png")
        cv.imwrite(str(out / written[-1]), check.reclosed.frame)
    return written


def format_checks(checks: Sequence[ClipCheck]) -> str:
    """One row a clip: when each frame was taken, its corners and edges, and the camera's shift."""

    def cells(pick: Pick | None, fps: float, opened: bool) -> str:
        if pick is None:
            return f"{'-':>6} {'-':>4} {'-':>7} {'-':>7}"
        tag = ("yes" if pick.detection.tag is not None else "no") if opened else "-"
        width = f"{pick.edge_width_px:.2f}" if pick.edge_width_px is not None else "-"
        return f"{pick.index / fps:6.1f} {tag:>4} {len(pick.detection.landmarks):7d} {width:>7}"

    lines = [
        f"{'clip':10s} {'shut s':>6} {'tag':>4} {'corners':>7} {'edge px':>7}   "
        f"{'open s':>6} {'tag':>4} {'corners':>7} {'edge px':>7}   {'shift px':>8}"
    ]
    for check in checks:
        shift = f"{check.shift_px:.2f}" if check.shift_px is not None else "-"
        lines.append(
            f"{check.name:10s} {cells(check.shut, check.fps, False)}   "
            f"{cells(check.opened, check.fps, True)}   {shift:>8}"
        )
        lines += [f"  problem: {text}" for text in check.problems]
        lines += [f"  note: {text}" for text in check.notes]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("clips", type=Path, nargs="+", help="one video a spot, T01.MOV and so on")
    parser.add_argument("--out", type=Path, required=True, help="the view set's folder")
    parser.add_argument(
        "--moving", type=int, nargs="*", default=[], help="markers on the panel that opens"
    )
    parser.add_argument("--rig", type=Path, default=RIG_FILE, help="the rig file with the markers")
    parser.add_argument("--force", action="store_true", help="replace frames already in --out")
    args = parser.parse_args(argv)

    names = [clip.stem for clip in args.clips]
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise SystemExit(f"clips with the same name would overwrite each other: {twice}")
    try:
        markers = load_marker_set(args.rig)
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"{args.rig}: {error}") from error
    unknown = sorted(set(args.moving) - set(markers.landmark_ids))
    if unknown:
        raise SystemExit(f"--moving {unknown}: not landmark markers of {args.rig}")
    if not args.force:
        there = [
            f"{name}_{state}.png"
            for name in names
            for state in ("close", "open", "2_close")
            if (args.out / f"{name}_{state}.png").exists()
        ]
        if there:
            raise SystemExit(f"{args.out} has {', '.join(there)}: --force replaces them")

    args.out.mkdir(parents=True, exist_ok=True)
    detector = marker_detector(markers)
    checks = [check_clip(clip, detector, markers, set(args.moving)) for clip in sorted(args.clips)]
    compare_takes(checks, set(markers.landmark_ids) - set(args.moving))
    for check in checks:
        write_frames(check, args.out)
    print(format_checks(checks))
    troubled = [check.name for check in checks if check.problems]
    if troubled:
        raise SystemExit(f"\n{len(troubled)} clips have problems: {', '.join(troubled)}")
    print(f"\nwrote the frames of {len(checks)} clips to {args.out}")


if __name__ == "__main__":
    main()
