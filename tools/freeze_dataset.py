"""Freeze an evaluation dataset: the atlas, the clicks and the board poses, with the media's hashes.

The frozen folder, eval/datasets/<name>/, is what tools/evaluate.py reads, and
it is kept in git; the media stay private, named in its manifest by SHA-256
(see smc_eval.dataset). A test set is a view set recorded apart from the
atlas, scored by the evaluation; a build set is the view set the atlas was
built from.

With --verify, nothing is frozen: the media an existing dataset was frozen
from are checked, still there and unchanged.
"""

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from smc_core.calibration import load_calibration
from smc_core.contracts import load_clicks
from smc_eval.dataset import (
    DatasetError,
    Role,
    check_media,
    freeze,
    read_manifest,
    videos_in,
)

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "eval" / "datasets"


def git_commit(root: Path) -> str | None:
    found = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    if found.returncode != 0:
        return None
    return found.stdout.strip() or None


def camera_file(folder: Path, camera_id: str) -> Path:
    """The intrinsics in folder calibrated for camera_id."""
    for path in sorted(folder.glob("*.yml")):
        if load_calibration(str(path))["camera_id"] == camera_id:
            return path
    raise DatasetError(f"no intrinsics for {camera_id} in {folder}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="the dataset's name, its folder in --out")
    parser.add_argument("--atlas", type=Path, help="the atlas file; its .report.json beside it")
    parser.add_argument(
        "--test", type=Path, action="append", default=[], help="a held-out view set folder"
    )
    parser.add_argument(
        "--build", type=Path, action="append", default=[], help="the atlas's view set folder"
    )
    parser.add_argument(
        "--videos", type=Path, action="append", default=[], help="a folder of the source videos"
    )
    parser.add_argument("--intrinsics", type=Path, default=ROOT / "calib" / "intrinsics")
    parser.add_argument("--rig", type=Path, default=ROOT / "calib" / "rig.yaml")
    parser.add_argument("--root", type=Path, default=ROOT, help="the workspace")
    parser.add_argument("--out", type=Path, default=DATASETS, help="where datasets are frozen")
    parser.add_argument("--verify", action="store_true", help="check the media of a dataset")
    args = parser.parse_args(argv)

    folder = args.out / args.name
    try:
        if args.verify:
            problems = check_media(read_manifest(folder), args.root)
            if problems:
                raise SystemExit("\n".join(problems))
            print(f"{folder}: every source file is there, unchanged")
            return

        if args.atlas is None or not args.test:
            parser.error("--atlas and at least one --test are needed to freeze")
        camera_id = load_clicks(args.test[0] / "clicks.json").camera_id
        sets: list[tuple[Path, Role]] = [(path, "test") for path in args.test]
        sets += [(path, "build") for path in args.build]
        manifest = freeze(
            folder,
            name=args.name,
            root=args.root,
            atlas_file=args.atlas,
            camera_file=camera_file(args.intrinsics, camera_id),
            rig_file=args.rig,
            videos=[video for videos in args.videos for video in videos_in(videos)],
            sets=sets,
            frozen_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            git_commit=git_commit(args.root),
        )
    except DatasetError as error:
        raise SystemExit(str(error)) from error

    print(f"frozen: {folder}")
    print(f"  atlas {manifest.asset_id} v{manifest.atlas_version}, camera {manifest.camera_id}")
    print(f"  {len(manifest.videos)} source videos")
    for view_set in manifest.sets:
        print(f"  {view_set.role} set {view_set.name}: {len(view_set.frames)} frames")


if __name__ == "__main__":
    main()
