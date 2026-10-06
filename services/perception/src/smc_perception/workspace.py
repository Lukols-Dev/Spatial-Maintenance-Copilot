"""The workspace on disk, and the one way the service reaches into it.

    <root>/calib/intrinsics/*.yml        cameras
    <root>/calib/rig.yaml                boards
    <root>/data/views/<set>/             view sets: images and clicks.json
    <root>/data/atlas/<asset_id>.json    atlases, each beside <asset_id>.report.json

A path built from a request is checked twice: its names must match a pattern
with no separators, and the path, symlinks resolved, must stay inside the
folder it belongs to and inside the root. Listings skip whatever fails either
check, so they show only what the other endpoints will serve.
"""

import os
import re
import secrets
import stat
from datetime import datetime
from pathlib import Path

from smc_perception.errors import Conflict, Invalid, NotFound
from smc_perception.settings import workspace_root

NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
IMAGE_FILE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._ -]*\.(?i:png|jpe?g)$"
CLICKS_FILE = "clicks.json"
REPORT_SUFFIX = ".report.json"
# The formats save_calibration writes, chosen by the extension.
CALIBRATION_SUFFIXES = {".yml", ".yaml", ".json", ".xml"}

_NAME = re.compile(NAME_PATTERN)
_IMAGE_FILE = re.compile(IMAGE_FILE_PATTERN)


def is_name(value: str) -> bool:
    """A valid view set name or asset id."""
    return _NAME.fullmatch(value) is not None


def is_image_file(value: str) -> bool:
    return _IMAGE_FILE.fullmatch(value) is not None


def check_name(value: str, what: str) -> str:
    if not is_name(value):
        raise Invalid(
            f"{what} {value!r} is not a valid name: use up to 64 letters, digits, "
            "'.', '_' or '-', starting with a letter or digit"
        )
    return value


class WorkspaceFiles:
    """Paths of one workspace root, which must already be resolved."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.intrinsics_dir = root / "calib" / "intrinsics"
        self.rig_file = root / "calib" / "rig.yaml"
        self.views_dir = root / "data" / "views"
        self.atlas_dir = root / "data" / "atlas"

    def relative(self, path: Path) -> str:
        """How a message names path: from the root, never absolutely."""
        return (
            path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else path.name
        )

    def inside(self, path: Path, folder: Path) -> Path | None:
        """path with symlinks resolved, or None when it leads out of folder or the root."""
        real = path.resolve()
        if real.is_relative_to(folder.resolve()) and real.is_relative_to(self.root):
            return real
        return None

    def contained(self, path: Path, folder: Path) -> Path:
        real = self.inside(path, folder)
        if real is None:
            raise NotFound(f"{self.relative(path)} leads outside the workspace")
        return real

    def folder_for_writing(self, folder: Path) -> Path:
        """folder, created when missing, after checking it stays inside the root.

        The check comes first, so a data/ that is a symlink to elsewhere never
        gets folders made in it.
        """
        if self.inside(folder, self.root) is None:
            raise Conflict(f"{self.relative(folder)} leads outside the workspace")
        folder.mkdir(parents=True, exist_ok=True)
        return folder.resolve()

    # ---- cameras -------------------------------------------------------------

    def calibration_files(self) -> list[Path]:
        if not self.intrinsics_dir.is_dir():
            return []
        return [
            entry
            for entry in sorted(self.intrinsics_dir.iterdir())
            if entry.suffix.lower() in CALIBRATION_SUFFIXES
            and not entry.name.startswith(".")
            and _is_file(self.inside(entry, self.intrinsics_dir))
        ]

    # ---- view sets -----------------------------------------------------------

    def view_set_names(self) -> list[str]:
        if not self.views_dir.is_dir():
            return []
        return [
            entry.name
            for entry in sorted(self.views_dir.iterdir())
            if is_name(entry.name) and _is_dir(self.inside(entry, self.views_dir))
        ]

    def view_set(self, name: str) -> Path:
        """The folder of an existing view set, symlinks resolved."""
        check_name(name, "view set")
        folder = self.contained(self.views_dir / name, self.views_dir)
        if not folder.is_dir():
            raise NotFound(f"no view set named {name!r}")
        return folder

    def images(self, folder: Path) -> list[Path]:
        """The images of a view set folder, sorted by file name."""
        return [
            entry
            for entry in sorted(folder.iterdir(), key=lambda path: path.name)
            if is_image_file(entry.name) and _is_file(self.inside(entry, folder))
        ]

    def image(self, name: str, file: str) -> Path:
        folder = self.view_set(name)
        if not is_image_file(file):
            raise Invalid(f"{file!r} is not the name of a PNG or JPEG file")
        path = self.contained(folder / file, folder)
        if not path.is_file():
            raise NotFound(f"no image {file!r} in view set {name!r}")
        return path

    def clicks_file(self, folder: Path) -> Path | None:
        """The clicks file of a view set folder, or None when it has none."""
        path = folder / CLICKS_FILE
        if not path.exists():
            return None
        if self.inside(path, folder) is None:
            raise NotFound(f"{self.relative(path)} leads outside the workspace")
        return path

    # ---- atlases -------------------------------------------------------------

    def atlas_ids(self) -> list[str]:
        if not self.atlas_dir.is_dir():
            return []
        found = []
        for entry in sorted(self.atlas_dir.iterdir()):
            asset_id = entry.name.removesuffix(".json")
            if (
                asset_id != entry.name
                and not entry.name.endswith(REPORT_SUFFIX)
                and is_name(asset_id)
                and _is_file(self.inside(entry, self.atlas_dir))
            ):
                found.append(asset_id)
        return found

    def atlas_file(self, asset_id: str) -> Path:
        check_name(asset_id, "asset id")
        return self.contained(self.atlas_dir / f"{asset_id}.json", self.atlas_dir)

    def report_file(self, asset_id: str) -> Path:
        check_name(asset_id, "asset id")
        return self.contained(self.atlas_dir / f"{asset_id}{REPORT_SUFFIX}", self.atlas_dir)


def _is_file(path: Path | None) -> bool:
    return path is not None and path.is_file()


def _is_dir(path: Path | None) -> bool:
    return path is not None and path.is_dir()


def current_workspace() -> WorkspaceFiles:
    """The workspace of this request; SMC_WORKSPACE is read again every time."""
    return WorkspaceFiles(workspace_root())


def write_atomic(path: Path, data: bytes) -> None:
    """Replace path with data, so a reader sees the old file or the new one, never a part.

    The temporary file sits next to path, since a rename is atomic only within
    one file system, and its name starts with a dot, which no listing shows.
    It is created like any new file, so the umask applies; a file that existed
    keeps its permissions.
    """
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def modified_at(path: Path) -> datetime:
    """When path last changed, in the server's time zone, to the second."""
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().replace(microsecond=0)


def changed_at(path: Path) -> datetime:
    """modified_at, or now when path cannot be read: for listings, which must not fail."""
    try:
        return modified_at(path)
    except OSError:
        return now()


def now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)
