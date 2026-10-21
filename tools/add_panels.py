"""Give an atlas the panels its target can be behind: the faces of the asset's box.

The box is axis-aligned in the atlas frame and given by its smallest and its
largest corner, in mm. Each --face names one of its faces (x-, x+, y-, y+, z-,
z+; x- is the face at the smaller x) as a panel. The atlas is written back with
those panels, replacing any it had, and every other field as it was.

--moving names the landmarks on a panel that opens: they are left out of a
frame that shows the target's tag, since the panel is then open.

For the cabinet of the 2026-10-09 recordings, in the frame of rig board B
(up is -z, the front faces +y):

    uv run tools/add_panels.py data/atlas/cabinet-manual.json --version 3 \\
        --box 154 -434 -372 754 -34 0 --face y+=flap --face x-=left_side \\
        --face x+=right_side --face z-=top --face y-=back --face z+=bottom \\
        --moving flap=flap_top_left,flap_right,flap_bottom
"""

import argparse
from pathlib import Path

from pydantic import ValidationError
from smc_core.contracts import Atlas, load_atlas
from smc_core.xray import FACES, box_panels


def face_name(text: str) -> tuple[str, str]:
    face, separator, name = text.partition("=")
    if not separator or face not in FACES or not name:
        raise argparse.ArgumentTypeError(
            f"{text!r}: expected FACE=ID with FACE one of {sorted(FACES)}"
        )
    return face, name


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("atlas", type=Path, help="the atlas file (.json)")
    parser.add_argument(
        "--box",
        type=float,
        nargs=6,
        required=True,
        metavar=("X0", "Y0", "Z0", "X1", "Y1", "Z1"),
        help="the smallest and the largest corner of the asset's box, mm",
    )
    parser.add_argument("--face", type=face_name, action="append", required=True, help="FACE=ID")
    parser.add_argument(
        "--moving",
        action="append",
        default=[],
        metavar="PANEL=ID,ID",
        help="landmarks on a panel that opens: landmark ids, or m<marker> for a marker's corners",
    )
    parser.add_argument("--version", help="the atlas's new version; default: as it was")
    parser.add_argument("--out", type=Path, help="where to write; default: the atlas file")
    args = parser.parse_args(argv)

    atlas = load_atlas(args.atlas)
    names = dict(args.face)
    if len(names) != len(args.face):
        raise SystemExit("a face is named twice")
    try:
        panels = box_panels(
            (args.box[0], args.box[1], args.box[2]), (args.box[3], args.box[4], args.box[5]), names
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    moving: dict[str, str] = {}
    for text in args.moving:
        panel, separator, ids = text.partition("=")
        if not separator or not ids:
            raise SystemExit(f"--moving {text!r}: expected PANEL=ID,ID")
        for item in ids.split(","):
            matched = [
                landmark.id
                for landmark in atlas.landmarks
                if landmark.id == item or landmark.id.startswith(f"{item}_")
            ]
            if not matched:
                raise SystemExit(f"--moving {text!r}: no landmark {item!r} in the atlas")
            moving.update(dict.fromkeys(matched, panel))
    landmarks = [
        landmark.model_copy(update={"moves_with": moving.get(landmark.id)})
        for landmark in atlas.landmarks
    ]
    update: dict[str, object] = {"panels": panels, "landmarks": landmarks}
    if args.version:
        update["version"] = args.version
    # Validated again, so a duplicate panel id stops the write.
    try:
        written = Atlas.model_validate(atlas.model_copy(update=update).model_dump())
    except ValidationError as error:
        raise SystemExit(str(error)) from error
    out = args.out or args.atlas
    out.write_text(written.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        f"{out}: {len(panels)} panels ({', '.join(panel.id for panel in panels)}), version {written.version}"
    )


if __name__ == "__main__":
    main()
