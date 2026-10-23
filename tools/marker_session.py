"""A recording session of the marked asset: from the phone's videos to an atlas, a test set and a verdict.

A session is a folder of data/, filled by sort and read by process:

    <session>/atlas/atlas_close.MOV    a walk-around with the panel shut and the rig board in sight
    <session>/atlas/atlas_open.MOV     the same with the panel open and the target's tag in sight
    <session>/tripod/T01.MOV ...       one clip a tripod spot (tools/viewpoint_clips.py)
    <session>/calib/calib.MOV          optional: the calibration board, to check the calibration

sort takes the videos as the phone named them, IMG_0812.MOV and on, in the order
they were recorded, and gives each its role from the recording card (CARD, or
--roles, which also takes calib for a calibration video). Each is first glanced
at against its role: the rig board through the walk-arounds, the tag never in a
shut clip and in a spot's clip only at its end, the calibration board in calib.
Nothing moves without --apply.

process runs the steps in order, each printing its numbers:

1. the stored calibration held against calib, when there is one (tools/check_calibration.py);
2. the walk-arounds' frames that show the rig board, their markers as clicks, less
   the frames whose board pose disagrees with the rest;
3. the atlas built from them, as the Atlas page builds it, into data/atlas/;
4. its panels fitted to the markers and the tape (tools/fit_panels.py);
5. the atlas held against an earlier build (tools/compare_atlases.py);
6. the tripod clips' shut and open frames (tools/viewpoint_clips.py), their markers as clicks;
7. a dataset frozen into <session>/check/ and evaluated there.

It ends with a verdict on the recordings, given while the rig board still lies
where it lay: GO, the board may be taken away; RE-RECORD, and what; or HOLD,
when a number needs a look first. Nothing is written to eval/: once the verdict
is GO, tools/freeze_dataset.py freezes the dataset there.

    uv run tools/marker_session.py sort ~/Downloads/session data/cabinet-aruco/2026-10-23
    make marker-session SESSION=data/cabinet-aruco/2026-10-23 FLOOR_MM=5
"""

import argparse
import logging
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2 as cv
import numpy as np
from add_panels import moving_landmarks, with_panels
from check_calibration import check_calibration, format_check
from compare_atlases import compare, format_comparison
from evaluate import environment, write
from export_views import board_test, video_frames
from fit_panels import face_markers, fit_box, fit_face, format_fit
from freeze_dataset import camera_file, git_commit
from smc_core.board_pose import board_in_view, board_view_pose
from smc_core.calibration import Intrinsics, create_board, load_calibration
from smc_core.contracts import Atlas, Clicks, load_atlas
from smc_core.images import read_images
from smc_core.markers import (
    DEFAULT_TARGET_ID,
    MarkerSet,
    detect,
    load_marker_set,
    mark_images,
    marker_detector,
    marker_points,
)
from smc_core.rig import load_rig_board
from smc_core.video import read_video_frames
from smc_core.xray import box_panels
from viewpoint_clips import (
    ClipCheck,
    check_clip,
    compare_takes,
    format_checks,
    is_take,
    marker_of,
    write_frames,
)

ROOT = Path(__file__).resolve().parents[1]
# The recording card of 2026-10-22, in the order it is recorded: the two
# walk-arounds, then the tripod spots, each clip ending with the panel shut again:
# its repeat. The camera keeps its calibration of 2026-10-05, so there is no
# calibration video.
CARD = (
    "atlas_close",
    "atlas_open",
    "T01",
    "T02",
    "T03",
    "T04",
    "T05",
    "T06",
    "T07",
    "T08",
    "T09",
    "T10",
    "T11",
    "T12",
)
VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v", ".avi"}
# Frames a clip is glanced at in, spread over it.
GLANCES = 12
# The walk-arounds' frames: the sharpest of every n, as the Atlas page imported the
# 2026-10-15 walk-arounds (export_views.py keeps 15 unless told).
WINDOW = 10
# Beyond these an atlas point is too loose to trust: re-record what it is seen in.
LANDMARK_SIGMA_MM = 2.0
TARGET_SIGMA_MM = 3.0
# The tape and the markers may disagree by this much before the scale needs a look.
SCALE_GAP_MM = 10.0
# Below this share of truths inside their 95% region, or with any false accept, hold.
INSIDE_SHARE = 0.8
# A walk-around frame whose board pose puts the markers this far, at the median,
# from where the other frames put them is left out of the atlas: the rig board
# seen small and at a slant can pose the camera mirrored, and one such frame
# moved a marker of the 2026-10-23 walk-arounds by 17 cm.
DISAGREE_PX = 10.0
# The fewest frames a point is triangulated from to judge a frame by it.
JUDGE_VIEWS = 3


# ---- sort ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Glance:
    """What a few frames spread over a clip show."""

    seconds: float
    frames: int
    calibration_board: int
    rig_board: int
    tags: list[bool]


def folder_of(role: str) -> str:
    if role == "calib":
        return "calib"
    return "atlas" if role.startswith("atlas_") else "tripod"


def recording_order(path: Path) -> tuple[int, str]:
    """IMG_0812.MOV sorts as 812: the phone numbers its videos as it records them."""
    numbers = re.findall(r"\d+", path.stem)
    return (int(numbers[0]) if numbers else -1, path.name)


def glance(
    video: Path,
    calibration: tuple[cv.aruco.CharucoDetector, cv.aruco.CharucoBoard],
    rig: tuple[cv.aruco.CharucoDetector, cv.aruco.CharucoBoard],
    detector: cv.aruco.ArucoDetector,
    markers: MarkerSet,
) -> Glance:
    capture = cv.VideoCapture(video, cv.CAP_FFMPEG)
    try:
        count = int(capture.get(cv.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv.CAP_PROP_FPS) or 30.0
    finally:
        capture.release()
    step = max(1, count // GLANCES)
    frames = [frame for _, frame in read_video_frames(video, step)][:GLANCES]
    return Glance(
        seconds=count / fps,
        frames=len(frames),
        calibration_board=sum(board_in_view(*calibration, frame) for frame in frames),
        rig_board=sum(board_in_view(*rig, frame) for frame in frames),
        tags=[detect(detector, markers, frame).tag is not None for frame in frames],
    )


def role_problems(role: str, seen: Glance, without_truth: set[str]) -> list[str]:
    """What the glance shows that the role does not allow."""
    half = seen.frames // 2
    if role == "calib":
        return ["the calibration board is in few frames"] if seen.calibration_board < half else []
    if role.startswith("atlas_"):
        problems = ["the rig board is in few frames"] if seen.rig_board < half else []
        if role == "atlas_close" and any(seen.tags):
            problems.append("the tag is in sight: was the panel shut?")
        if role == "atlas_open" and not any(seen.tags):
            problems.append("the tag is never in sight: was the panel open?")
        return problems
    if is_take(role):
        return ["the tag is in sight in a take of the shut panel"] if any(seen.tags) else []
    problems = []
    if seen.tags and seen.tags[0]:
        problems.append("the tag is in sight at the start: was the panel shut?")
    if role not in without_truth and not (seen.tags and seen.tags[-1]):
        problems.append("the tag is not in sight at the end: opened, with the tag in view?")
    return problems


def sort(args: argparse.Namespace) -> None:
    videos = sorted(
        (path for path in args.incoming.iterdir() if path.suffix.lower() in VIDEO_SUFFIXES),
        key=recording_order,
    )
    roles = args.roles or list(CARD)
    if len(videos) != len(roles):
        listed = "\n".join(f"  {video.name}" for video in videos)
        raise SystemExit(
            f"{len(videos)} videos in {args.incoming}, {len(roles)} roles on the card "
            f"({', '.join(roles)}):\n{listed}\n"
            "delete the failed takes, or name the roles in order with --roles"
        )

    markers = load_marker_set(args.rig)
    detector = marker_detector(markers)
    boards = {}
    for key in ("calibration_board", args.board):
        rig = load_rig_board(args.rig, key)
        board = create_board(
            rig["squares_x"],
            rig["squares_y"],
            rig["square_mm"],
            rig["marker_mm"],
            rig["dictionary_id"],
            rig["marker_ids"],
        )
        boards[key] = (cv.aruco.CharucoDetector(board), board)

    moves: list[tuple[Path, Path]] = []
    troubled = 0
    print(f"{'video':16s} {'s':>6s}  {'role':12s} goes to")
    for video, role in zip(videos, roles, strict=True):
        seen = glance(video, boards["calibration_board"], boards[args.board], detector, markers)
        target = args.session / folder_of(role) / f"{role}{video.suffix}"
        print(f"{video.name:16s} {seen.seconds:6.1f}  {role:12s} {target}")
        problems = role_problems(role, seen, set(args.no_truth))
        if target.exists() and not args.force:
            problems.append(f"{target} exists: --force replaces it")
        for problem in problems:
            print(f"  problem: {problem}")
        troubled += bool(problems)
        moves.append((video, target))

    if troubled and not args.force:
        raise SystemExit(f"\n{troubled} videos do not fit their roles: nothing moved")
    if not args.apply:
        print("\nevery video fits its role; --apply moves them")
        return
    for video, target in moves:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(video, target)
    print(f"\nmoved {len(moves)} videos into {args.session}")


# ---- process ---------------------------------------------------------------------------


@dataclass
class Verdict:
    """What the session's numbers say about the recordings, while the rig board still lies there."""

    rerecord: list[str] = field(default_factory=list)
    hold: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def format(self) -> str:
        if self.rerecord:
            lines = ["RE-RECORD, with the rig board where it lies:"]
        elif self.hold:
            lines = ["HOLD: look at these before the rig board is moved:"]
        else:
            lines = ["GO: the recordings hold; the rig board may be taken away."]
        lines += [f"  re-record: {text}" for text in self.rerecord]
        lines += [f"  look: {text}" for text in self.hold]
        lines += [f"  note: {text}" for text in self.notes]
        return "\n".join(lines)


def section(title: str) -> None:
    print(f"\n== {title}")


def clear_frames(folder: Path, force: bool) -> None:
    """An empty view set folder: frames already there are a mistake unless --force replaces them."""
    there = [path for path in folder.glob("*") if path.suffix.lower() in {".png", ".json"}]
    if there and not force:
        raise SystemExit(f"{folder} has {len(there)} files: --force replaces them")
    for path in there:
        path.unlink()
    folder.mkdir(parents=True, exist_ok=True)


def mark_folder(
    folder: Path,
    markers: MarkerSet,
    camera_id: str,
    moving: Sequence[int],
    opened: Callable[[str], bool],
) -> Clicks:
    """The folder's markers as its clicks.json, the panel's left out of every frame taken with it open.

    mark_images leaves them out where the tag is in sight; a frame of an open
    panel that misses the tag would otherwise mark them where they no longer are.
    """
    marked = mark_images(read_images(folder), markers, DEFAULT_TARGET_ID, moving)
    views = {
        name: {
            point: pixel
            for point, pixel in points.items()
            if not opened(name) or marker_of(point) not in moving
        }
        for name, points in marked.views.items()
    }
    clicks = Clicks(
        camera_id=camera_id,
        points=marker_points(markers, DEFAULT_TARGET_ID),
        views={name: points for name, points in views.items() if points},
    )
    (folder / "clicks.json").write_text(clicks.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"  {folder.name}: {len(clicks.views)} of {marked.images} frames with markers")
    counts = ", ".join(
        f"{marker}: {marked.marker_images[marker]}" for marker in markers.landmark_ids
    )
    print(f"  frames a marker is in: {counts}; the tag: {marked.tag_images}")
    return clicks


def _triangulated(observations: list[tuple[np.ndarray, np.ndarray, np.ndarray]]) -> np.ndarray:
    """The point seen at these normalised image positions by cameras at these poses, by linear least squares."""
    rows = []
    for rotation, tvec, (x, y) in observations:
        projection = np.hstack([rotation, tvec.reshape(3, 1)])
        rows += [x * projection[2] - projection[0], y * projection[2] - projection[1]]
    _, _, vt = np.linalg.svd(np.array(rows))
    return vt[-1][:3] / vt[-1][3]


def frame_residuals(
    seen: dict[str, dict[str, np.ndarray]],
    poses: dict[str, tuple[np.ndarray, np.ndarray]],
    intrinsics: Intrinsics,
) -> dict[str, float]:
    """Each frame's median distance between the markers it saw and where the frames together put them, px."""
    matrix, dist = intrinsics["camera_matrix"], intrinsics["dist_coeffs"]
    residuals: dict[str, list[float]] = {}
    for views in seen.values():
        views = {name: pixel for name, pixel in views.items() if name in poses}
        if len(views) < JUDGE_VIEWS:
            continue
        pixels = np.array(list(views.values()))
        normalised = cv.undistortPoints(pixels.reshape(-1, 1, 2), matrix, dist).reshape(-1, 2)
        position = _triangulated(
            [(*poses[name], xy) for name, xy in zip(views, normalised, strict=True)]
        )
        for name, pixel in views.items():
            rvec, _ = cv.Rodrigues(poses[name][0])
            projected, _ = cv.projectPoints(
                position.reshape(1, 3), rvec, poses[name][1], matrix, dist
            )
            residuals.setdefault(name, []).append(float(np.linalg.norm(projected.ravel() - pixel)))
    return {name: float(np.median(values)) for name, values in residuals.items()}


def disagreeing_frames(
    folder: Path, clicks: Clicks, intrinsics: Intrinsics, board: cv.aruco.CharucoBoard
) -> tuple[dict[str, float], float]:
    """Frames whose board pose disagrees with the others, by their median residual; and the others' median.

    Each point is triangulated from every posed frame that sees it, and each
    frame is judged by how far it reprojects those points from where it saw
    them: a frame with a wrong pose misses all of them. The frames that stay are
    measured again without the ones left out, which pulled every point a little.
    """
    detector = cv.aruco.CharucoDetector(board)
    poses: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name in clicks.views:
        frame = cv.imread(str(folder / name))
        pose = board_view_pose(
            detector, board, frame, intrinsics, np.random.default_rng(0), samples=0
        )
        if pose is not None:
            poses[name] = (pose["rotation"], pose["tvec"])
    seen: dict[str, dict[str, np.ndarray]] = {}
    for name, points in clicks.views.items():
        for point, pixel in points.items():
            seen.setdefault(point, {})[name] = np.array(pixel, np.float64)
    first = frame_residuals(seen, poses, intrinsics)
    disagreeing = {name: value for name, value in first.items() if value >= DISAGREE_PX}
    staying = {name: pose for name, pose in poses.items() if name not in disagreeing}
    again = frame_residuals(seen, staying, intrinsics)
    return disagreeing, float(np.median(list(again.values()))) if again else 0.0


def leave_out(folder: Path, clicks: Clicks, names: Sequence[str]) -> Clicks:
    """The view set without these frames: their files removed, their clicks dropped."""
    for name in names:
        (folder / name).unlink(missing_ok=True)
    kept = Clicks(
        camera_id=clicks.camera_id,
        points=clicks.points,
        views={name: points for name, points in clicks.views.items() if name not in names},
    )
    (folder / "clicks.json").write_text(kept.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return kept


def check_atlas_points(atlas: Atlas, verdict: Verdict) -> None:
    """Every marker the atlas holds, how tight; a loose one, or the target, wants more views."""
    sigmas: dict[int, float] = {}
    for landmark in atlas.landmarks:
        marker = marker_of(landmark.id)
        if marker is not None:
            sigmas[marker] = max(sigmas.get(marker, 0.0), landmark.sigma_mm)
    listed = ", ".join(f"{marker} {sigma:.1f}" for marker, sigma in sorted(sigmas.items()))
    print(f"  markers, the sigma of their loosest corner in mm: {listed}")
    print(f"  target: sigma {atlas.target.sigma_mm:.2f} mm")
    loose = {marker: sigma for marker, sigma in sigmas.items() if sigma > LANDMARK_SIGMA_MM}
    for marker, sigma in sorted(loose.items()):
        verdict.rerecord.append(
            f"the walk-arounds: marker {marker} is located to {sigma:.1f} mm only; "
            "film it more squarely, with the rig board in sight"
        )
    if atlas.target.sigma_mm > TARGET_SIGMA_MM:
        verdict.rerecord.append(
            f"atlas_open: the target is located to {atlas.target.sigma_mm:.1f} mm only; "
            "film its tag from more sides"
        )


def process(args: argparse.Namespace) -> None:
    # The service builds the atlas as the Atlas page does; it is imported here, as
    # evaluate.py imports it, so that sort needs none of it.
    from smc_eval.dataset import DatasetError, freeze, load_dataset, videos_in
    from smc_eval.evaluate import evaluate
    from smc_perception.atlases import build
    from smc_perception.errors import WorkspaceError
    from smc_perception.models import AtlasBuildRequest
    from smc_perception.workspace import WorkspaceFiles

    root = args.root.resolve()
    session = args.session.resolve()
    rig_file = root / "calib" / "rig.yaml"
    markers = load_marker_set(rig_file)
    moving = list(args.moving)
    intrinsics_file = camera_file(root / "calib" / "intrinsics", args.camera_id)
    verdict = Verdict()

    section("1. the camera's calibration")
    calib_clips = sorted((session / "calib").glob("*")) if (session / "calib").is_dir() else []
    if calib_clips:
        rig = load_rig_board(rig_file, "calibration_board")
        board = create_board(
            rig["squares_x"],
            rig["squares_y"],
            rig["square_mm"],
            rig["marker_mm"],
            rig["dictionary_id"],
            rig["marker_ids"],
        )
        try:
            calibration = check_calibration(
                calib_clips[0], load_calibration(str(intrinsics_file)), board, step=30
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error
        print(format_check(calibration))
        if not calibration.fits:
            verdict.hold.append(
                "the stored calibration does not describe today's frames; the videos stay "
                "good, but the atlas wants a new calibration first"
            )
    else:
        print("  no calibration video")
        verdict.notes.append("no calibration video: the stored calibration is not checked")

    section("2. the walk-arounds' frames and markers")
    walk = root / "data" / "views" / args.walkaround
    clear_frames(walk, args.force)
    keep = board_test(rig_file, args.board)
    walk_clips = sorted((session / "atlas").glob("atlas_*"))
    if not walk_clips:
        raise SystemExit(f"no walk-around in {session / 'atlas'}")
    for clip in walk_clips:
        count = 0
        for name, frame in video_frames(clip, WINDOW, False, True, keep):
            cv.imwrite(str(walk / name), frame)
            count += 1
        print(f"  {clip.name}: {count} frames with the rig board")
    clicks = mark_folder(
        walk, markers, args.camera_id, moving, lambda name: name.startswith("atlas_open")
    )
    rig_b = load_rig_board(rig_file, args.board)
    board_b = create_board(
        rig_b["squares_x"],
        rig_b["squares_y"],
        rig_b["square_mm"],
        rig_b["marker_mm"],
        rig_b["dictionary_id"],
        rig_b["marker_ids"],
    )
    disagreeing, typical = disagreeing_frames(
        walk, clicks, load_calibration(str(intrinsics_file)), board_b
    )
    leave_out(walk, clicks, sorted(disagreeing))
    print(f"  a frame's markers lie a median {typical:.1f} px from where all the frames put them")
    print(
        f"  left out, their board pose {DISAGREE_PX:.0f} px or more off: {len(disagreeing)} frames"
    )
    for name, residual in sorted(disagreeing.items(), key=lambda item: -item[1])[:5]:
        print(f"    {name}: {residual:.0f} px")

    section("3. the atlas")
    request = AtlasBuildRequest(
        asset_id=args.asset_id,
        view_set=args.walkaround,
        camera_id=args.camera_id,
        board=args.board,
        target_id=DEFAULT_TARGET_ID,
        target_extent_mm=(args.target_extent[0], args.target_extent[1], args.target_extent[2]),
        click_sigma_px=args.click_sigma,
        target_centre_sigma_mm=args.target_centre_sigma,
        target_tag_depth_mm=args.target_extent[2],
        version=args.version,
    )
    try:
        built = build(WorkspaceFiles(root), request)
    except WorkspaceError as error:
        raise SystemExit(f"the atlas cannot be built: {error}") from error
    report = built.report
    if report is not None:
        print(f"  {len(report.posed_views)} frames posed on the rig board")
    check_atlas_points(built.atlas, verdict)

    section("4. the panels")
    atlas_file = root / "data" / "atlas" / f"{args.asset_id}.json"
    atlas = load_atlas(atlas_file)
    width, depth, height = args.size
    # The markers that move are those on the front, which opens.
    opens = f"{args.front[0]}=" + ",".join(f"m{marker}" for marker in moving)
    try:
        box = fit_box(
            fit_face(atlas, *args.front),
            fit_face(atlas, *args.top),
            [fit_face(atlas, *side) for side in args.side],
            (width, depth, height),
            args.floor_mm,
            args.other_side,
        )
        atlas = with_panels(
            atlas,
            box_panels(box.minimum, box.maximum, box.names),
            moving_landmarks(atlas, [opens]),
            None,
        )
    except ValueError as error:
        verdict.rerecord.append(f"the walk-arounds: {error}")
        print(f"  {error}")
    else:
        atlas_file.write_text(atlas.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(format_fit(box, width, height))
        for what, measured, taped in (
            ("width", box.width_mm, width),
            ("height", box.height_mm, height),
        ):
            if measured is not None and abs(measured - taped) > SCALE_GAP_MM:
                verdict.hold.append(
                    f"the atlas's {what} is {measured:.0f} mm, the tape's {taped:.0f}: "
                    "measure the rig board's squares and the asset again"
                )

    if args.previous is not None:
        section("5. against the earlier build")
        try:
            comparison = compare(load_atlas(args.previous), atlas, args.compare)
        except ValueError as error:
            print(f"  {error}")
        else:
            print(format_comparison(comparison))

    section("6. the tripod's spots")
    tripod = root / "data" / "views" / args.tripod
    clear_frames(tripod, args.force)
    clips = sorted(
        path for path in (session / "tripod").glob("*") if path.suffix.lower() in VIDEO_SUFFIXES
    )
    if not clips:
        raise SystemExit(f"no tripod clip in {session / 'tripod'}")
    detector = marker_detector(markers)
    checks: list[ClipCheck] = [check_clip(clip, detector, markers, set(moving)) for clip in clips]
    compare_takes(checks, set(markers.landmark_ids) - set(moving))
    for check in checks:
        write_frames(check, tripod)
    print(format_checks(checks))
    for check in checks:
        verdict.rerecord += [f"{check.name}: {problem}" for problem in check.problems]
        if not is_take(check.name) and not check.problems and not check.has_truth:
            if check.name in args.no_truth:
                verdict.notes.append(f"{check.name}: no truth, as the card plans")
            else:
                verdict.rerecord.append(
                    f"{check.name}: the tag is not in sight with the panel open, so the spot "
                    "has no truth; aim so the box's tag shows once the panel opens"
                )
    mark_folder(tripod, markers, args.camera_id, moving, lambda name: name.endswith("_open.png"))

    section("7. the evaluation")
    # Without a model every agent turn logs that it had none; the traces say so already.
    logging.getLogger("smc_agent.copilot").setLevel(logging.ERROR)
    check_root = session / "check"
    dataset_folder = check_root / f"{args.asset_id}-{session.name}"
    if dataset_folder.exists():
        shutil.rmtree(dataset_folder)
    try:
        freeze(
            dataset_folder,
            name=dataset_folder.name,
            root=root,
            atlas_file=atlas_file,
            camera_file=intrinsics_file,
            rig_file=rig_file,
            videos=videos_in(session),
            sets=[(tripod, "test"), (walk, "build")],
            frozen_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            git_commit=git_commit(root),
        )
        results, traces = evaluate(
            load_dataset(dataset_folder, root),
            evaluated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            environment=environment(root),
        )
    except DatasetError as error:
        raise SystemExit(f"the dataset cannot be frozen: {error}") from error
    write(check_root / "results", results, traces)
    localisation, decisions = results.localisation, results.decisions
    print(
        f"  {localisation.viewpoints} viewpoints, {localisation.with_truth} with a truth, "
        f"{localisation.localised} localised"
    )
    if localisation.error_px.median is not None:
        print(f"  target error: median {localisation.error_px.median:.1f} px")
    inside = localisation.inside_95
    print(f"  truth inside the 95% region: {inside.k}/{inside.n}")
    print(
        f"  accepted {decisions.accepted_inside + decisions.accepted_outside}, "
        f"of them with the truth outside {decisions.accepted_outside}"
    )
    print(f"  the full report: {check_root / 'results' / 'report.md'}")
    if decisions.accepted_outside:
        verdict.hold.append(
            f"{decisions.accepted_outside} results were accepted with the truth outside their "
            "region: see the report's table before the board goes"
        )
    if inside.n and inside.k / inside.n < INSIDE_SHARE:
        verdict.hold.append(
            f"the truth is inside the 95% region in {inside.k} of {inside.n} viewpoints only"
        )

    section("verdict")
    print(verdict.format())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    steps = parser.add_subparsers(dest="step", required=True)

    sorting = steps.add_parser("sort", help="give the phone's videos their roles")
    sorting.add_argument("incoming", type=Path, help="the folder the videos came into")
    sorting.add_argument("session", type=Path, help="the session's folder in data/")
    sorting.add_argument("--roles", type=lambda text: text.split(","), help="ROLE,ROLE in order")
    sorting.add_argument("--board", default="rig_board_b", help="the rig board of the walk-arounds")
    sorting.add_argument("--no-truth", nargs="*", default=["T11"], help="spots with no tag in view")
    sorting.add_argument("--rig", type=Path, default=ROOT / "calib" / "rig.yaml")
    sorting.add_argument("--apply", action="store_true", help="move the videos into place")
    sorting.add_argument("--force", action="store_true", help="move them despite the problems")

    running = steps.add_parser("process", help="atlas, test set, evaluation and verdict")
    running.add_argument("session", type=Path, help="the session's folder in data/")
    running.add_argument("--root", type=Path, default=ROOT, help="the workspace")
    running.add_argument("--asset-id", required=True)
    running.add_argument("--version", required=True, help="the new atlas's version")
    running.add_argument("--camera-id", required=True)
    running.add_argument("--board", required=True, help="the rig board that fixes the frame")
    running.add_argument("--walkaround", required=True, help="the view set the atlas is built from")
    running.add_argument("--tripod", required=True, help="the test view set")
    running.add_argument(
        "--moving", type=int, nargs="+", required=True, help="the markers on the front, which opens"
    )
    running.add_argument("--front", type=face_markers, required=True, help="PANEL=MARKER,MARKER")
    running.add_argument("--top", type=face_markers, required=True, help="PANEL=MARKER,MARKER")
    running.add_argument("--side", type=face_markers, action="append", required=True)
    running.add_argument("--other-side", help="the side with no markers, when one is marked")
    running.add_argument(
        "--size", type=float, nargs=3, required=True, metavar=("WIDTH", "DEPTH", "HEIGHT")
    )
    running.add_argument("--floor-mm", type=float, required=True, help="the board's thickness")
    running.add_argument(
        "--target-extent", type=float, nargs=3, required=True, metavar=("ACROSS", "UP", "DEEP")
    )
    running.add_argument("--click-sigma", type=float, required=True)
    running.add_argument("--target-centre-sigma", type=float, required=True)
    running.add_argument("--previous", type=Path, help="an earlier build of the atlas")
    running.add_argument("--compare", type=int, nargs="+", help="the markers that stayed")
    running.add_argument("--no-truth", nargs="*", default=[], help="spots with no tag in view")
    running.add_argument("--force", action="store_true", help="replace the view sets' frames")

    args = parser.parse_args(argv)
    if args.step == "sort":
        sort(args)
    else:
        process(args)


if __name__ == "__main__":
    main()
