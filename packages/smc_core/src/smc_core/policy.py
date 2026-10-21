"""The decision on a localisation: shown as reliable, or a move to a better viewpoint.

The geometry measures and this module judges. Each Check holds one measurement
of the Localisation against one limit of the Policy, and the Decision carries
both, so a reader sees which threshold turned which fact into the verdict. A
camera frame adds the measurement of its blur. The move follows from geometry
as well: where the estimated pose puts the target and every landmark of the
atlas relative to the frame, and which landmarks the camera cannot see because
it stands where the atlas never saw them from. A blurred frame asks for the
camera to be held still before any move.

decide() is pure: no I/O and no randomness, so a localisation always gets the
same decision.
"""

import math
from collections import Counter
from typing import Literal

import cv2 as cv
import numpy as np

from smc_core.calibration import Intrinsics
from smc_core.contracts import (
    Action,
    Atlas,
    Check,
    Decision,
    Failure,
    FrameQuality,
    Localisation,
    Policy,
    Pose,
    Vec2,
    View,
)
from smc_core.pose import in_frame, project_landmarks

DEFAULT_POLICY = Policy()

# These choose which way to move and never make a result reliable, so they are
# fixed here rather than calibrated in the Policy.
MIN_FILL = 0.25  # the landmarks' bounding box / the frame, below which moving closer helps
MAX_OFF_CENTRE = 0.25  # the box centre's offset, as a share of the frame width or height
# When the pose alone spreads the target over less than this share of the
# region, the rest comes from the atlas, which no viewpoint changes.
POSE_SHARE = 0.5

# Each failure: its name in a reason, the move, and the fact the move follows from.
FAILURES: dict[Failure, tuple[str, Action, str]] = {
    Failure.TOO_FEW_CORRESPONDENCES: (
        "too few correspondences",
        Action.MOVE_BACK,
        "too few landmarks in view to fit a pose",
    ),
    Failure.DEGENERATE_GEOMETRY: (
        "degenerate geometry",
        Action.MOVE_BACK,
        "the landmarks in view lie on one line",
    ),
    Failure.PNP_FAILED: (
        "PnP failed",
        Action.MOVE_BACK,
        "no pose agrees with enough landmarks in view",
    ),
    Failure.TARGET_BEHIND_CAMERA: (
        "target behind the camera",
        Action.MOVE_BACK,
        "the pose puts part of the target behind the camera",
    ),
    Failure.UNSTABLE_POSE: (
        "unstable pose",
        Action.MOVE_CLOSER,
        "the pose is lost in almost every Monte Carlo sample",
    ),
}

# The edge of the frame each move looks beyond, and where it sees the landmarks from.
EDGES = {
    Action.MOVE_LEFT: "left",
    Action.MOVE_RIGHT: "right",
    Action.MOVE_UP: "top",
    Action.MOVE_DOWN: "bottom",
}
SIDES = {
    Action.MOVE_LEFT: "left of",
    Action.MOVE_RIGHT: "right of",
    Action.MOVE_UP: "above",
    Action.MOVE_DOWN: "below",
}
FURTHER = {
    Action.MOVE_LEFT: "left",
    Action.MOVE_RIGHT: "right",
    Action.MOVE_UP: "up",
    Action.MOVE_DOWN: "down",
}


def decide(
    localisation: Localisation,
    view: View,
    atlas: Atlas,
    intrinsics: Intrinsics,
    policy: Policy = DEFAULT_POLICY,
    frame: FrameQuality | None = None,
) -> Decision:
    """Hold the localisation of view against the policy and choose the next action.

    view gives the number of landmarks matched when the localisation failed
    before measuring anything. atlas and intrinsics give where the pose puts
    every landmark, observed or not, which the framing of a move needs. frame
    is the blur of a camera frame; a view clicked by hand has none.

    Every check is listed, passed or not. The result is reliable only without
    a failure and with every check passed, and then the action is ACCEPT.
    """
    known = {landmark.id for landmark in atlas.landmarks}
    matched = sum(observation.landmark_id in known for observation in view.observations)
    checks = _checks(localisation, matched, policy)
    if frame is not None:
        checks.append(_check("edge_width_px", frame.edge_width_px, policy.max_edge_width_px, "<="))
    if localisation.failure is None and all(check.passed for check in checks):
        return Decision(
            reliable=True,
            action=Action.ACCEPT,
            reasons=[],
            move_reason="",
            checks=checks,
            policy=policy,
        )

    action, move_reason = _move(localisation, view, atlas, intrinsics, _blurred(checks))
    return Decision(
        reliable=False,
        action=action,
        reasons=_reasons(localisation, checks),
        move_reason=move_reason,
        checks=checks,
        policy=policy,
    )


# ---- checks ------------------------------------------------------------------


def _checks(localisation: Localisation, matched: int, policy: Policy) -> list[Check]:
    """Every measurement against its limit; a value that was never measured is None."""
    quality, target, region = localisation.quality, localisation.target, localisation.uncertainty
    observed: float = matched
    inliers = inlier_ratio = rms = coverage = None
    if quality is not None:
        observed, inliers = quality.observed, quality.inliers
        inlier_ratio, rms = quality.inlier_ratio, quality.rms_reprojection_px
        coverage = quality.image_coverage
    framed = None if target is None else float(target.in_frame)
    stability = ratio = None
    if region is not None and region.samples > 0:
        stability = region.failed_samples / region.samples
    if region is not None and target is not None and target.radius_px > 0:
        ratio = region.ellipse.semi_major_px / target.radius_px
    return [
        _check("landmarks", observed, policy.min_landmarks, ">="),
        _check("inliers", inliers, policy.min_inliers, ">="),
        _check("inlier_ratio", inlier_ratio, policy.min_inlier_ratio, ">="),
        _check("rms_reprojection_px", rms, policy.max_rms_reprojection_px, "<="),
        _check("image_coverage", coverage, policy.min_image_coverage, ">="),
        _check("target_in_frame", framed, 1.0, ">="),
        _check("pose_stability", stability, policy.max_failed_sample_ratio, "<="),
        _check("region_ratio", ratio, policy.max_region_ratio, "<="),
    ]


def _check(name: str, value: float | None, limit: float, op: Literal[">=", "<="]) -> Check:
    if value is not None and not math.isfinite(value):
        value = None  # JSON carries no NaN or infinity, and neither passes anything
    passed = value is not None and (value >= limit if op == ">=" else value <= limit)
    return Check(
        name=name,
        value=None if value is None else float(value),
        limit=float(limit),
        op=op,
        passed=passed,
    )


def _reasons(localisation: Localisation, checks: list[Check]) -> list[str]:
    """The failure first, then one fact for each failed check.

    After a failure, a check without a value needs no fact of its own: the
    failure is why it was never measured.
    """
    reasons = []
    if localisation.failure is not None:
        reasons.append(f"localisation failed: {FAILURES[localisation.failure][0]}")
    for check in checks:
        if check.passed:
            continue
        if check.value is not None:
            reasons.append(_reason(check.name, check.value, check.limit))
        elif localisation.failure is None:
            # Only a target that projects to no area leaves a value out here.
            reasons.append(f"{check.name.replace('_', ' ')} cannot be computed")

    region = localisation.uncertainty
    region_failed = any(check.name == "region_ratio" and not check.passed for check in checks)
    if (
        region_failed
        and region is not None
        and region.pose_only.semi_major_px < POSE_SHARE * region.ellipse.semi_major_px
    ):
        reasons.append("the atlas uncertainty dominates the region")
    return reasons


def _reason(name: str, value: float, limit: float) -> str:
    """A failed check as a short fact: the measurement, then what the policy needs."""
    match name:
        case "landmarks":
            return f"{_count(value, 'landmark')} matched, needs ≥ {limit:g}"
        case "inliers":
            return f"{_count(value, 'inlier')}, needs ≥ {limit:g}"
        case "inlier_ratio":
            return f"inlier ratio {_shown(value, limit, 2)}, needs ≥ {limit:g}"
        case "rms_reprojection_px":
            return f"RMS reprojection {_shown(value, limit, 2)} px, needs ≤ {limit:g} px"
        case "image_coverage":
            percent = _shown(100 * value, 100 * limit, 1)
            return f"landmarks cover {percent} % of the frame, needs ≥ {100 * limit:g} %"
        case "target_in_frame":
            return "the target centre projects outside the frame"
        case "pose_stability":
            percent = _shown(100 * value, 100 * limit, 1)
            return f"{percent} % of Monte Carlo samples failed, needs ≤ {100 * limit:g} %"
        case "region_ratio":
            ratio = _shown(value, limit, 2)
            times = "\N{MULTIPLICATION SIGN}"
            return f"95 % region is {ratio} {times} the target radius, needs ≤ {limit:g}"
        case "edge_width_px":
            return f"marker edges {_shown(value, limit, 1)} px wide, needs ≤ {limit:g} px"
        case _:
            raise ValueError(f"no reason worded for check {name!r}")


def _count(value: float, noun: str) -> str:
    count = round(value)
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _shown(value: float, limit: float, places: int) -> str:
    """value to `places` decimals, or more where fewer would print it as the limit it misses."""
    text = f"{value:.{places}f}"
    while text == f"{limit:.{places}f}" and places < 6:
        places += 1
        text = f"{value:.{places}f}"
    return text


# ---- the move ----------------------------------------------------------------


def _blurred(checks: list[Check]) -> float | None:
    """The edge width of a frame the policy finds blurred; None for a sharp frame or a clicked view."""
    for check in checks:
        if check.name == "edge_width_px" and check.value is not None and not check.passed:
            return check.value
    return None


def _move(
    localisation: Localisation,
    view: View,
    atlas: Atlas,
    intrinsics: Intrinsics,
    blurred: float | None = None,
) -> tuple[Action, str]:
    """The action rules in order: a blurred frame, a failure, a target outside the
    frame, landmarks turned away from the camera, the framing.

    Blur comes first: it moves the markers a still camera would see sharp, and
    may hide some, so whatever else a blurred frame shows says little about
    where the camera should go.
    """
    if blurred is not None:
        return (
            Action.HOLD_STILL,
            f"marker edges smeared over {blurred:.1f} px: the camera moved while the frame was taken",
        )
    if localisation.failure is not None:
        _, action, fact = FAILURES[localisation.failure]
        return action, fact

    image_size = intrinsics["image_size"]
    target = localisation.target
    if target is not None and not target.in_frame:
        action = _toward(*_offset(target.centre_px, image_size))
        return action, f"the target centre projects beyond the {EDGES[action]} edge of the frame"

    pose = localisation.pose
    if pose is not None:
        turned = _turned_away(pose, view, atlas)
        if turned is not None:
            return turned

    projections = {} if pose is None else project_landmarks(atlas, pose, intrinsics)
    return _framing(list(projections.values()), image_size)


def _turned_away(pose: Pose, view: View, atlas: Atlas) -> tuple[Action, str] | None:
    """The move toward where the unobserved landmarks facing away were seen from.

    A landmark the view does not observe faces away when the camera stands
    outside the cone it was seen within while the atlas was built. The move is
    the mean change from each one's direction to the camera to the direction
    it was seen from, in the camera frame; its larger image component picks
    the side. None when no landmark faces away, or the atlas does not say.
    """
    observed = {observation.landmark_id for observation in view.observations}
    rotation, _ = cv.Rodrigues(np.array(pose.rvec, np.float64))
    centre = -rotation.T @ np.array(pose.tvec_mm, np.float64)

    away: list[str] = []
    changes: list[np.ndarray] = []
    for landmark in atlas.landmarks:
        if landmark.id in observed or landmark.seen_from is None:
            continue
        offset = centre - np.array(landmark.position_mm, np.float64)
        distance = float(np.linalg.norm(offset))
        if distance == 0 or landmark.seen_within_deg is None:
            continue
        to_camera: np.ndarray = offset / distance
        seen_from = np.array(landmark.seen_from, np.float64)
        off_deg = math.degrees(math.acos(max(-1.0, min(1.0, float(seen_from @ to_camera)))))
        if off_deg > landmark.seen_within_deg:
            away.append(landmark.id)
            changes.append(seen_from - to_camera)
    if not away:
        return None

    change = rotation @ np.mean(changes, axis=0)
    action = _toward(float(change[0]), float(change[1]))
    ids = ", ".join(sorted(away))
    return action, f"landmarks {ids} face away from the camera, seen from further {FURTHER[action]}"


def _framing(pixels: list[Vec2 | None], image_size: tuple[int, int]) -> tuple[Action, str]:
    """The move that frames every landmark of the atlas, where the pose projects them.

    A landmark behind the camera (None) is outside on no particular side. One
    beyond a corner counts for the edge it is further beyond, measured as for
    the target: offset from the centre over half the width or height.
    """
    inside = [pixel for pixel in pixels if pixel is not None and in_frame(pixel, image_size)]
    outside = len(pixels) - len(inside)
    if outside:
        edges = Counter(
            _toward(*_offset(pixel, image_size))
            for pixel in pixels
            if pixel is not None and not in_frame(pixel, image_size)
        )
        if edges:
            action, count = edges.most_common(1)[0]
            if count > outside / 2:
                return action, f"landmarks extend beyond the {EDGES[action]} edge of the frame"
        if len(edges) > 1:
            return Action.MOVE_BACK, "landmarks extend beyond several edges of the frame"
        return Action.MOVE_BACK, "some landmarks lie behind the camera"
    if not inside:
        return Action.MOVE_BACK, "the atlas has no landmarks"

    width, height = image_size
    xs, ys = [u for u, _ in inside], [v for _, v in inside]
    fill = (max(xs) - min(xs)) * (max(ys) - min(ys)) / (width * height)
    fills = f"landmarks fill {_shown(100 * fill, 100 * MIN_FILL, 0)} % of the frame"
    if fill < MIN_FILL:
        return Action.MOVE_CLOSER, fills
    off_x = ((max(xs) + min(xs)) / 2 - width / 2) / width
    off_y = ((max(ys) + min(ys)) / 2 - height / 2) / height
    if max(abs(off_x), abs(off_y)) > MAX_OFF_CENTRE:
        action = _toward(off_x, off_y)
        return action, f"landmarks sit {SIDES[action]} the frame centre"
    return Action.MOVE_CLOSER, fills


def _offset(pixel: Vec2, image_size: tuple[int, int]) -> tuple[float, float]:
    """How far a pixel is from the frame centre, in half widths and half heights."""
    width, height = image_size
    return (pixel[0] - width / 2) / (width / 2), (pixel[1] - height / 2) / (height / 2)


def _toward(dx: float, dy: float) -> Action:
    """The move along the axis of the larger offset; image y grows downward."""
    if abs(dx) >= abs(dy):
        return Action.MOVE_RIGHT if dx > 0 else Action.MOVE_LEFT
    return Action.MOVE_DOWN if dy > 0 else Action.MOVE_UP
