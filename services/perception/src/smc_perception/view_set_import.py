"""POST /view-sets: a new view set from one video or from photos.

It does what tools/export_views.py does, so the PNG files are the same: the
sharpest frame of every window of a video, as the video plays, or every photo
in its sensor grid with the EXIF orientation ignored.

The set is built in a hidden folder next to the others and renamed into place
at the end, so it appears whole or not at all, and a failed import leaves
nothing behind.
"""

import os
import re
import secrets
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO, Literal, NamedTuple

import cv2 as cv
import numpy as np
from smc_core.images import read_images
from smc_core.video import read_video_frames, sharpest_per_window

from smc_perception.errors import Conflict, Invalid, WorkspaceError
from smc_perception.workspace import WorkspaceFiles, check_name, is_image_file

VIDEO_SUFFIXES = (".mov", ".mp4", ".m4v", ".avi", ".mkv")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
CHUNK_BYTES = 1 << 20


class Upload(NamedTuple):
    filename: str  # as the browser sent it
    file: BinaryIO


class _Plan(NamedTuple):
    kind: Literal["video", "images"]
    names: list[str]  # file name of each upload, without any folder


def import_view_set(
    workspace: WorkspaceFiles, name: str, window: int, uploads: list[Upload]
) -> Path:
    """Create data/views/<name>/ from the uploads and return its folder."""
    check_name(name, "view set")
    plan = _plan(uploads)
    views_dir = workspace.folder_for_writing(workspace.views_dir)
    target = views_dir / name
    if target.exists() or target.is_symlink():
        raise Conflict(f"view set {name!r} already exists")

    build = views_dir / f".import-{secrets.token_hex(6)}"
    build.mkdir()
    try:
        received = build / ".uploads"
        received.mkdir()
        if plan.kind == "video":
            video = received / f"video{Path(plan.names[0]).suffix.lower()}"
            _receive(uploads[0].file, video)
            frames = _video_frames(video, plan.names[0], window)
        else:
            for upload, file_name in zip(uploads, plan.names, strict=True):
                _receive(upload.file, received / file_name)
            frames = _photos(received)
        if _write_pngs(frames, build) == 0:
            raise Invalid(f"no frames could be read from {plan.names[0]}")
        shutil.rmtree(received)
        try:
            build.rename(target)
        except OSError as error:  # another import took the name meanwhile
            raise Conflict(f"view set {name!r} already exists") from error
    except BaseException:
        shutil.rmtree(build, ignore_errors=True)
        raise
    return target


def _plan(uploads: list[Upload]) -> _Plan:
    """Check the uploads make one video or a set of photos, before anything is stored."""
    if not uploads:
        raise Invalid("no files uploaded")
    # A folder upload may send "folder/IMG_1.jpg"; only the file name counts.
    names = [re.split(r"[\\/]", upload.filename)[-1] for upload in uploads]
    unsupported = [
        name or "(no name)"
        for name in names
        if not name.lower().endswith(VIDEO_SUFFIXES + IMAGE_SUFFIXES)
    ]
    if unsupported:
        raise Invalid(
            f"unsupported file type: {', '.join(unsupported)} "
            f"(use {', '.join(VIDEO_SUFFIXES + IMAGE_SUFFIXES)})"
        )

    videos = [name for name in names if name.lower().endswith(VIDEO_SUFFIXES)]
    if videos and len(names) > 1:
        raise Invalid("upload either one video or photos: " + ", ".join(names))
    if videos:
        return _Plan("video", names)

    outputs = [f"{Path(name).stem}.png" for name in names]
    not_allowed = [
        name for name, output in zip(names, outputs, strict=True) if not is_image_file(output)
    ]
    if not_allowed:
        raise Invalid(
            f"file names not allowed: {', '.join(not_allowed)} (use letters, digits, "
            "' ', '.', '_' or '-', starting with a letter or digit)"
        )
    # Compared without case: on macOS a.png and A.png are one file.
    stems: dict[str, list[str]] = {}
    for name in names:
        stems.setdefault(Path(name).stem.casefold(), []).append(name)
    duplicates = [", ".join(group) for group in stems.values() if len(group) > 1]
    if duplicates:
        raise Invalid(f"these would give the same PNG file: {'; '.join(duplicates)}")
    return _Plan("images", names)


def _receive(source: BinaryIO, path: Path) -> None:
    """Copy an upload to disk in chunks, never holding it in memory."""
    with path.open("wb") as file:
        shutil.copyfileobj(source, file, CHUNK_BYTES)


def _video_frames(video: Path, upload_name: str, window: int) -> Iterable[tuple[str, np.ndarray]]:
    frames = sharpest_per_window(read_video_frames(video), window)
    try:
        yield from frames
    except OSError as error:
        raise Invalid(f"cannot read {upload_name} as a video") from error


def _photos(folder: Path) -> Iterable[tuple[str, np.ndarray]]:
    try:
        yield from read_images(folder)
    except OSError as error:
        # read_images names the file by its full path; the user knows it by name.
        raise Invalid(str(error).replace(f"{folder}{os.sep}", "")) from error


def _write_pngs(frames: Iterable[tuple[str, np.ndarray]], folder: Path) -> int:
    """Write every frame as <label stem>.png, as export_views.py names them."""
    count = 0
    for label, frame in frames:
        path = folder / f"{Path(label).stem}.png"
        if not cv.imwrite(str(path), frame):
            raise WorkspaceError(f"cannot write {path.name}")
        count += 1
    return count
