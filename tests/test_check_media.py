"""The media guard: capture data stays out of the public repository, the web app's icons go in."""

import subprocess
import sys
from pathlib import Path

import cv2 as cv
import numpy as np

REPOSITORY = Path(__file__).resolve().parents[1]
GUARD = REPOSITORY / "tools" / "hooks" / "check_media.py"
ICONS = (
    "apps/web/app/apple-icon.png",
    "apps/web/public/icon-192.png",
    "apps/web/public/icon-512.png",
)


def put_png(root: Path, name: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    _, png = cv.imencode(".png", np.zeros((4, 4), np.uint8))
    path.write_bytes(png.tobytes())


def guard(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """The hook as pre-commit runs it: from the repository's root, on paths relative to it."""
    return subprocess.run(
        [sys.executable, str(GUARD), *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_web_app_icons_pass_and_a_picture_beside_them_does_not(tmp_path: Path) -> None:
    for name in (*ICONS, "apps/web/public/frame.png"):
        put_png(tmp_path, name)

    assert guard(tmp_path, *ICONS).returncode == 0
    refused = guard(tmp_path, "apps/web/public/frame.png")
    assert refused.returncode == 1
    assert "apps/web/public/frame.png" in refused.stderr


def test_an_icon_is_still_held_to_the_size_ceiling(tmp_path: Path) -> None:
    put_png(tmp_path, ICONS[0])

    refused = guard(tmp_path, "--max-kb", "0", ICONS[0])

    assert refused.returncode == 1
    assert "ceiling" in refused.stderr
