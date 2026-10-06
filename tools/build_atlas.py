"""Build a Component Atlas from views of the board and hand-marked points.

The printed board fixes the asset frame: origin at its top-left corner, x along
the first square count, y along the second, z completing a right-handed frame.
Every view in which the board is found gives the camera pose in that frame, and
every point marked in two or more such views is triangulated.
"""

import argparse
from pathlib import Path

import cv2 as cv
import numpy as np
from smc_core.atlas_build import AtlasReport, build_atlas
from smc_core.board_pose import ViewPose, pose_views
from smc_core.calibration import create_board, load_calibration
from smc_core.contracts import load_clicks
from smc_core.images import read_images
from smc_core.rig import load_rig_board

RIG_FILE = Path(__file__).resolve().parents[1] / "calib" / "rig.yaml"


def format_report(
    report: AtlasReport,
    poses: dict[str, ViewPose],
    target_id: str,
    target_sigma_mm: float,
    target_measured_mm: tuple[float, float, float] | None,
) -> str:
    """Text summary of an atlas build: the numbers to read before trusting it."""
    lines = [f"views with the board: {len(poses)}", "  corners  rms px  view"]
    for name, pose in sorted(poses.items()):
        lines.append(f"  {pose['corners']:7d}  {pose['rms_px']:6.2f}  {name}")
    for name in report["unposed_views"]:
        lines.append(f"  no board  {name}  (its clicks are not used)")

    lines += ["", "points in the board frame, mm:"]
    lines.append("  id                      x        y        z  sigma  views  worst px  angle")
    for point_id, estimate in report["points"].items():
        x, y, z = estimate["position_mm"]
        marker = "  <- target" if point_id == target_id else ""
        sigma = target_sigma_mm if point_id == target_id else estimate["sigma_mm"]
        lines.append(
            f"  {point_id:20s} {x:8.1f} {y:8.1f} {z:8.1f} {sigma:6.2f} "
            f"{report['views_per_point'][point_id]:6d} {estimate['residuals_px'].max():9.2f} "
            f"{estimate['ray_angle_deg']:5.1f}{marker}"
        )
    for point_id, reason in report["skipped"].items():
        lines.append(f"  {point_id:20s} skipped: {reason}")

    if target_measured_mm is not None:
        located = report["points"][target_id]["position_mm"]
        gap = float(np.linalg.norm(located - np.array(target_measured_mm)))
        lines += ["", f"target: {gap:.1f} mm between the triangulated and the measured position"]

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("views", type=Path, help="folder of exported views (see export_views.py)")
    parser.add_argument("--clicks", type=Path, required=True, help="JSON of marked points")
    parser.add_argument("--intrinsics", type=Path, required=True, help="calibration file (.yml)")
    parser.add_argument(
        "--board", required=True, help="board key in the rig file, e.g. rig_board_a"
    )
    parser.add_argument("--rig", type=Path, default=RIG_FILE, help="measured boards")
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--version", default="1")
    parser.add_argument("--target-id", required=True, help="the clicked point that is the target")
    parser.add_argument(
        "--target-extent",
        type=float,
        nargs=3,
        required=True,
        metavar=("X", "Y", "Z"),
        help="size of a box around the target in mm, along the board's x, y and z",
    )
    parser.add_argument(
        "--target-measured",
        type=float,
        nargs=3,
        metavar=("X", "Y", "Z"),
        help="target centre in the board frame measured with a ruler, for a cross-check",
    )
    parser.add_argument(
        "--click-sigma-px", type=float, default=2.0, help="how far a click may be from the truth"
    )
    parser.add_argument(
        "--target-centre-sigma-mm",
        type=float,
        default=5.0,
        help="how far the clicked centre of the target may be from its real centre",
    )
    parser.add_argument("--samples", type=int, default=200, help="Monte Carlo samples")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True, help="atlas file to write (.json)")
    args = parser.parse_args(argv)

    try:
        rig = load_rig_board(args.rig, args.board)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    board = create_board(
        rig["squares_x"],
        rig["squares_y"],
        rig["square_mm"],
        rig["marker_mm"],
        rig["dictionary_id"],
        rig["marker_ids"],
    )
    detector = cv.aruco.CharucoDetector(board)
    intrinsics = load_calibration(str(args.intrinsics))

    rng = np.random.default_rng(args.seed)
    poses = pose_views(
        read_images(args.views), detector, board, intrinsics, rng, samples=args.samples
    )

    atlas, report = build_atlas(
        poses,
        load_clicks(args.clicks),
        intrinsics,
        asset_id=args.asset_id,
        version=args.version,
        frame=f"board:{args.board}",
        target_id=args.target_id,
        target_extent_mm=(args.target_extent[0], args.target_extent[1], args.target_extent[2]),
        click_sigma_px=args.click_sigma_px,
        target_centre_sigma_mm=args.target_centre_sigma_mm,
        seed=args.seed,
    )

    measured = None
    if args.target_measured is not None:
        measured = (args.target_measured[0], args.target_measured[1], args.target_measured[2])
    print(format_report(report, poses, args.target_id, atlas.target.sigma_mm, measured))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(atlas.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"\nsaved: {args.out}")


if __name__ == "__main__":
    main()
