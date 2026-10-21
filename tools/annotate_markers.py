"""Mark the printed markers in a folder of frames: the clicks of a view set, with no clicking.

Every frame is searched for the markers of calib/rig.yaml (tools/gen_markers.py).
A landmark marker gives its four corners as points m<id>_<corner>. The
target's tag gives the target's point, its centre, and its four corners,
<target>_<corner>, which orient the target's box when the atlas is built with
--target-tag-depth. Markers on a part that opens (--moving) are left out of
every frame that shows the tag: there the part is open and its markers are
not where the atlas has them.

The result is the folder's clicks.json, as the annotator writes it, so the
atlas builder, the annotator, the Locate page and the evaluation read it as
they read clicks made by hand. The Atlas page runs the same search
(POST /view-sets/{name}/markers). Clicks already in the folder are kept unless
--force replaces them.

    uv run tools/annotate_markers.py data/views/cabinet-aruco-atlas \\
        --camera-id iphone11-1x-1080p-portrait --moving 50 51 52 53
"""

import argparse
from pathlib import Path

from smc_core.contracts import Clicks
from smc_core.images import read_images
from smc_core.markers import DEFAULT_TARGET_ID, load_marker_set, mark_images, marker_points

RIG_FILE = Path(__file__).resolve().parents[1] / "calib" / "rig.yaml"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("folder", type=Path, help="a folder of frames (see export_views.py)")
    parser.add_argument("--camera-id", required=True, help="the camera the frames were taken with")
    parser.add_argument("--rig", type=Path, default=RIG_FILE, help="the rig file with the markers")
    parser.add_argument("--target-id", default=DEFAULT_TARGET_ID, help="the target's point id")
    parser.add_argument(
        "--moving", type=int, nargs="*", default=[], help="markers on a part that opens"
    )
    parser.add_argument("--force", action="store_true", help="replace the folder's clicks.json")
    args = parser.parse_args(argv)

    out = args.folder / "clicks.json"
    if out.exists() and not args.force:
        raise SystemExit(f"{out} exists: its clicks are kept; --force replaces them")
    try:
        markers = load_marker_set(args.rig)
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"{args.rig}: {error}") from error
    unknown = sorted(set(args.moving) - set(markers.landmark_ids))
    if unknown:
        raise SystemExit(f"--moving {unknown}: not landmark markers of {args.rig}")

    marked = mark_images(read_images(args.folder), markers, args.target_id, args.moving)
    if not marked.views:
        raise SystemExit(f"{args.folder}: no marker of {args.rig} in {marked.images} frames")

    points = marker_points(markers, args.target_id)
    clicks = Clicks(camera_id=args.camera_id, points=points, views=marked.views)
    out.write_text(clicks.model_dump_json(indent=2) + "\n", encoding="utf-8")

    print(f"{out}: {len(marked.views)} of {marked.images} frames with markers")
    for marker in markers.landmark_ids:
        print(f"  marker {marker}: {marked.marker_images[marker]} frames")
    print(f"  target's tag {markers.target_id}: {marked.tag_images} frames")


if __name__ == "__main__":
    main()
