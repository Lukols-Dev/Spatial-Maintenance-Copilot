"""Give an atlas the panels of its asset's box, fitted to the markers stuck on the box's faces.

add_panels.py takes the box's corners as numbers; this finds them. Each face
named with its markers is the plane those markers lie on: square to the board
axis nearest their normal, at their mean along it. The box is axis-aligned in
the atlas frame (smc_core.xray), so the board must have lain square to the
asset; the angle between each face's normal and its axis says how square.

The front, the top and one side or both come from markers. The back is the
front moved by the measured depth into the asset, a side without markers is the
marked one moved by the measured width (--other-side names it), and the bottom
is the floor, which the board lies on, its printed face --floor-mm above it. The
height, and the width when both sides are marked, are then measured twice, by
the markers and by the tape, and the printout holds one against the other: a
gap of more than a few millimetres means that the atlas, or the tape, is off in
scale.

    uv run tools/fit_panels.py data/atlas/cabinet-aruco.json --size 610 340 380 \\
        --floor-mm 0 --front flap=50,51,52,53 --top top=54,55 \\
        --side left_side=56,57 --other-side right_side --moving flap=m50,m51,m52,m53
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from add_panels import moving_landmarks, with_panels
from smc_core.contracts import Atlas, Vec3, load_atlas
from smc_core.xray import box_panels

AXES = "xyz"
# The board lies flat, so the asset's top is square to the board's z axis.
VERTICAL = 2
# Beyond these the printout warns: the board lay this far off square to a face,
# the markers and the tape disagree by this much.
TILT_DEG = 2.0
GAP_MM = 5.0


@dataclass(frozen=True)
class FaceFit:
    """One face of the box, as the markers stuck on it put it."""

    panel: str
    markers: tuple[int, ...]
    axis: int
    inward: int  # +1 or -1: the asset lies on this side of the face, along the axis
    offset_mm: float
    flatness_mm: float  # RMS of the corners about the face's plane
    tilt_deg: float  # between the markers' normal and the axis


@dataclass(frozen=True)
class BoxFit:
    """The box: its two corners, which face is which panel, and its size by the markers."""

    minimum: Vec3
    maximum: Vec3
    names: dict[str, str]  # face of the box, x- to z+, to its panel
    faces: tuple[FaceFit, ...]
    width_mm: float | None  # None with one side marked: the width is the tape's
    height_mm: float


def face_markers(text: str) -> tuple[str, list[int]]:
    panel, separator, ids = text.partition("=")
    try:
        markers = [int(item) for item in ids.split(",")]
    except ValueError:
        markers = []
    if not separator or not panel or not markers:
        raise argparse.ArgumentTypeError(f"{text!r}: expected PANEL=MARKER,MARKER")
    return panel, markers


def fit_face(atlas: Atlas, panel: str, markers: Sequence[int]) -> FaceFit:
    """The plane of a face from the four corners of every listed marker the atlas has.

    The corners run as OpenCV orders a marker's, so their turn gives the normal
    that points into the surface the marker is stuck on.
    """
    positions = {landmark.id: np.array(landmark.position_mm) for landmark in atlas.landmarks}
    found: list[int] = []
    normals: list[np.ndarray] = []
    points: list[np.ndarray] = []
    for marker in markers:
        corners = [positions.get(f"m{marker}_{corner}") for corner in range(4)]
        if any(corner is None for corner in corners):
            continue
        c0, c1, c2, c3 = (np.asarray(corner) for corner in corners)
        normal = np.cross(c1 - c0, c3 - c0)
        normals.append(normal / np.linalg.norm(normal))
        points += [c0, c1, c2, c3]
        found.append(marker)
    if not found:
        raise ValueError(
            f"{panel}: none of the markers {list(markers)} has its corners in the atlas"
        )
    normal = np.sum(normals, axis=0)
    normal /= np.linalg.norm(normal)
    axis = int(np.argmax(np.abs(normal)))
    along = np.array(points)[:, axis]
    offset = float(along.mean())
    return FaceFit(
        panel=panel,
        markers=tuple(found),
        axis=axis,
        inward=1 if normal[axis] > 0 else -1,
        offset_mm=offset,
        flatness_mm=float(np.sqrt(np.mean((along - offset) ** 2))),
        tilt_deg=float(np.degrees(np.arccos(min(1.0, abs(float(normal[axis])))))),
    )


def fit_box(
    front: FaceFit,
    top: FaceFit,
    sides: Sequence[FaceFit],
    size_mm: tuple[float, float, float],
    floor_mm: float,
    other_side: str | None = None,
    back: str = "back",
    bottom: str = "bottom",
) -> BoxFit:
    """The box from its marked faces, the measured size and the floor; ValueError when they do not square.

    size_mm is the asset by tape: width, depth, height. With one side marked,
    other_side names the side across from it, the width away.
    """
    if len(sides) not in (1, 2) or (len(sides) == 1) == (other_side is None):
        raise ValueError("two marked sides, or one and the id of the other")
    across = sides[0].axis
    if top.axis != VERTICAL:
        raise ValueError(
            f"{top.panel}'s markers face along {AXES[top.axis]}, not z: does the board lie flat?"
        )
    if any(side.axis != across for side in sides) or len({front.axis, top.axis, across}) != 3:
        listed = ", ".join(f"{face.panel} on {AXES[face.axis]}" for face in (front, top, *sides))
        raise ValueError(f"the faces are not square to the board: {listed}")
    width, depth, _ = size_mm
    if len(sides) == 2:
        far, far_name = sides[1].offset_mm, sides[1].panel
        width_by_markers: float | None = abs(far - sides[0].offset_mm)
    else:
        far = sides[0].offset_mm + sides[0].inward * width
        far_name, width_by_markers = str(other_side), None
    # The floor lies below the board's printed face, the way the top's inside lies.
    floor = top.inward * floor_mm
    back_offset = front.offset_mm + front.inward * depth
    spans = {
        across: (sides[0].offset_mm, far),
        VERTICAL: (top.offset_mm, floor),
        front.axis: (front.offset_mm, back_offset),
    }
    lower = [min(spans[axis]) for axis in range(3)]
    upper = [max(spans[axis]) for axis in range(3)]

    def face(axis: int, offset: float) -> str:
        return f"{AXES[axis]}{'-' if offset == lower[axis] else '+'}"

    names = {
        face(front.axis, front.offset_mm): front.panel,
        face(front.axis, back_offset): back,
        face(VERTICAL, top.offset_mm): top.panel,
        face(VERTICAL, floor): bottom,
        face(across, sides[0].offset_mm): sides[0].panel,
        face(across, far): far_name,
    }
    if len(names) != 6:
        raise ValueError("two faces of the box fall on one place: are both sides marked apart?")
    return BoxFit(
        minimum=(lower[0], lower[1], lower[2]),
        maximum=(upper[0], upper[1], upper[2]),
        names=names,
        faces=(front, top, *sides),
        width_mm=width_by_markers,
        height_mm=abs(floor - top.offset_mm),
    )


def format_fit(box: BoxFit, width_mm: float, height_mm: float) -> str:
    """The faces as the markers put them, the box, and its size against the tape."""
    face_of = {panel: face for face, panel in box.names.items()}
    lines = [
        f"  {'panel':12s} {'face':4s} {'markers':16s} {'at mm':>8s} {'flat mm':>7s} {'tilt':>5s}"
    ]
    for fit in box.faces:
        markers = " ".join(str(marker) for marker in fit.markers)
        lines.append(
            f"  {fit.panel:12s} {face_of[fit.panel]:4s} {markers:16s} {fit.offset_mm:8.1f} "
            f"{fit.flatness_mm:7.2f} {fit.tilt_deg:4.1f}°"
        )
    lines.append(
        "  box: "
        + ", ".join(
            f"{AXES[axis]} {box.minimum[axis]:.1f}..{box.maximum[axis]:.1f}" for axis in range(3)
        )
        + " mm"
    )
    if box.width_mm is None:
        lines.append(f"  width between the sides: {width_mm:.0f} mm by the tape, one side marked")
    for what, measured, taped in (
        ("width between the sides", box.width_mm, width_mm),
        ("height from the floor", box.height_mm, height_mm),
    ):
        if measured is None:
            continue
        gap = measured - taped
        warning = "  <- check the scale" if abs(gap) > GAP_MM else ""
        lines.append(
            f"  {what}: {measured:.1f} mm by the markers, {taped:.0f} by the tape, {gap:+.1f}{warning}"
        )
    lines += [
        f"  {fit.panel}: the board lay {fit.tilt_deg:.1f}° off square to it; the panels are approximate"
        for fit in box.faces
        if fit.tilt_deg > TILT_DEG
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("atlas", type=Path, help="the atlas file (.json)")
    parser.add_argument(
        "--size",
        type=float,
        nargs=3,
        required=True,
        metavar=("WIDTH", "DEPTH", "HEIGHT"),
        help="the asset by tape, mm: across the front, front to back, floor to top",
    )
    parser.add_argument(
        "--floor-mm",
        type=float,
        required=True,
        help="the board's thickness: its face above the floor",
    )
    parser.add_argument("--front", type=face_markers, required=True, help="PANEL=MARKER,MARKER")
    parser.add_argument("--top", type=face_markers, required=True, help="PANEL=MARKER,MARKER")
    parser.add_argument(
        "--side", type=face_markers, action="append", required=True, help="PANEL=MARKER, or twice"
    )
    parser.add_argument("--other-side", help="the side with no markers, when one is marked")
    parser.add_argument("--back", default="back", help="the back's panel id")
    parser.add_argument("--bottom", default="bottom", help="the bottom's panel id")
    parser.add_argument(
        "--moving",
        action="append",
        default=[],
        metavar="PANEL=ID,ID",
        help="landmarks on a panel that opens, as add_panels.py takes them",
    )
    parser.add_argument("--version", help="the atlas's new version; default: as it was")
    parser.add_argument("--out", type=Path, help="where to write; default: the atlas file")
    args = parser.parse_args(argv)

    atlas = load_atlas(args.atlas)
    width, depth, height = args.size
    try:
        box = fit_box(
            fit_face(atlas, *args.front),
            fit_face(atlas, *args.top),
            [fit_face(atlas, *side) for side in args.side],
            (width, depth, height),
            args.floor_mm,
            args.other_side,
            args.back,
            args.bottom,
        )
        panels = box_panels(box.minimum, box.maximum, box.names)
        written = with_panels(atlas, panels, moving_landmarks(atlas, args.moving), args.version)
    except ValueError as error:  # pydantic's ValidationError among them
        raise SystemExit(str(error)) from error
    out = args.out or args.atlas
    out.write_text(written.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(format_fit(box, width, height))
    print(f"{out}: {len(panels)} panels, version {written.version}")


if __name__ == "__main__":
    main()
