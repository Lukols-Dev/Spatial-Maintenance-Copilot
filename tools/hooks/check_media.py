"""
check_media.py - pre-commit guard for a public computer-vision repository.

Three rules, all of them about a repository that anyone on the internet can read:

1. Video and camera-raw files never belong in git. They belong in S3, referenced
   from eval/datasets/*.manifest.json by key and SHA256.
2. Still images are allowed only under an explicit allowlist of directories.
   Everything else is capture data and follows rule 1.
3. An allowed still image must not carry EXIF GPS data and must be small.
   A frame of an engine bay is harmless. The same frame tagged with the
   coordinates of the garage it was shot in is not.

Zero third-party dependencies on purpose: a hook that needs Pillow installed is
a hook that gets skipped on a fresh clone.

Exit code 0 when everything passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

# Never committed, under any path.
BLOCKED_EXT = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
    ".webm",
    ".mts",
    ".cr2",
    ".cr3",
    ".arw",
    ".nef",
    ".raf",
    ".dng",
    ".orf",
    ".rw2",
}

# Allowed, but only inside ALLOWED_DIRS and only after the EXIF and size checks.
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".heic"}

# Directories where a still image is a deliberate artefact rather than capture data.
ALLOWED_DIRS = ("fixtures/", "docs/", "tools/hooks/testdata/")

# EXIF tag 0x8825 is the GPS IFD pointer. Its presence means coordinates are embedded.
EXIF_GPS_IFD = 0x8825


def _read(path: str, size: int = -1) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(size)


def _jpeg_exif_payload(blob: bytes) -> bytes | None:
    """Return the TIFF payload of the APP1/Exif segment, or None."""
    if not blob.startswith(b"\xff\xd8"):
        return None
    i = 2
    n = len(blob)
    while i + 4 <= n:
        if blob[i] != 0xFF:
            return None
        marker = blob[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:  # start of scan, no metadata beyond this point
            return None
        seg_len = struct.unpack(">H", blob[i + 2 : i + 4])[0]
        seg = blob[i + 4 : i + 2 + seg_len]
        if marker == 0xE1 and seg.startswith(b"Exif\x00\x00"):
            return seg[6:]
        i += 2 + seg_len
    return None


def _tiff_has_gps(tiff: bytes) -> bool:
    """Walk IFD0 of a TIFF header and report whether a GPS IFD pointer exists."""
    if len(tiff) < 8:
        return False
    if tiff[:2] == b"II":
        endian = "<"
    elif tiff[:2] == b"MM":
        endian = ">"
    else:
        return False
    try:
        (ifd0_offset,) = struct.unpack(endian + "I", tiff[4:8])
        if ifd0_offset + 2 > len(tiff):
            return False
        (count,) = struct.unpack(endian + "H", tiff[ifd0_offset : ifd0_offset + 2])
        base = ifd0_offset + 2
        for k in range(count):
            entry = base + k * 12
            if entry + 12 > len(tiff):
                return False
            (tag,) = struct.unpack(endian + "H", tiff[entry : entry + 2])
            if tag == EXIF_GPS_IFD:
                return True
    except struct.error:
        return False
    return False


def has_gps(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    blob = _read(path)
    if ext in (".jpg", ".jpeg"):
        payload = _jpeg_exif_payload(blob)
        return _tiff_has_gps(payload) if payload else False
    if ext in (".tif", ".tiff"):
        return _tiff_has_gps(blob)
    if ext == ".png":
        # PNG stores EXIF in an optional eXIf chunk.
        idx = blob.find(b"eXIf")
        return idx != -1 and _tiff_has_gps(blob[idx + 4 :])
    # HEIC: no cheap dependency-free parse. Treat as unknown and therefore unsafe.
    return ext == ".heic"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("filenames", nargs="*")
    ap.add_argument(
        "--max-kb",
        type=int,
        default=300,
        help="size ceiling for an allowed still image (default 300)",
    )
    args = ap.parse_args()

    problems: list[str] = []

    for path in args.filenames:
        norm = path.replace(os.sep, "/")
        ext = os.path.splitext(norm)[1].lower()

        if ext in BLOCKED_EXT:
            problems.append(
                f"{norm}\n"
                f"    Video and raw capture files do not go in git.\n"
                f"    Upload to S3 and reference it from eval/datasets/*.manifest.json."
            )
            continue

        if ext not in IMAGE_EXT:
            continue

        if not norm.startswith(ALLOWED_DIRS):
            problems.append(
                f"{norm}\n"
                f"    Still images are allowed only under: {', '.join(ALLOWED_DIRS)}\n"
                f"    Capture data belongs in S3 with a manifest entry, not in the repo."
            )
            continue

        size_kb = os.path.getsize(norm) / 1024
        if size_kb > args.max_kb:
            problems.append(
                f"{norm}\n"
                f"    {size_kb:.0f} kB exceeds the {args.max_kb} kB ceiling for committed images.\n"
                f"    Fixtures should be crops, not full frames."
            )

        if has_gps(norm):
            problems.append(
                f"{norm}\n"
                f"    Carries EXIF GPS data. This is a public repository.\n"
                f"    Strip metadata before committing, for example:\n"
                f"      exiftool -all= {norm}"
            )

    if problems:
        sys.stderr.write("\nMedia guard rejected the following files:\n\n")
        for p in problems:
            sys.stderr.write(f"  {p}\n\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
