"""The judge's recordings: each clip converted, held to the camera's size and codec, and listed."""

import argparse
import json
import shutil
from pathlib import Path

import cv2 as cv
import judge_recordings
import numpy as np
import pytest
from judge_recordings import build, clip_title, converter


def write_clip(path: Path, size: tuple[int, int], frames: int = 10) -> Path:
    writer = cv.VideoWriter(str(path), cv.VideoWriter.fourcc(*"mp4v"), 30.0, size)
    for index in range(frames):
        writer.write(np.full((size[1], size[0], 3), 20 * index % 255, np.uint8))
    writer.release()
    return path


def test_a_clip_is_named_with_its_title() -> None:
    assert clip_title("data/demo_1.MOV=From the left side") == (
        Path("data/demo_1.MOV"),
        "From the left side",
    )
    with pytest.raises(argparse.ArgumentTypeError, match="CLIP=TITLE"):
        clip_title("data/demo_1.MOV")


def test_the_index_lists_every_clip_in_the_order_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        judge_recordings,
        "probe",
        lambda path: {"codec": "avc1", "width": 1080, "height": 1920, "seconds": 12.5},
    )
    clips = [(Path("demo_2.MOV"), "Too close"), (Path("demo_1.MOV"), "From the left side")]

    entries = build(clips, tmp_path / "out", lambda source, target: target.write_bytes(b"mp4"))

    index = json.loads((tmp_path / "out" / "index.json").read_text())
    assert index == {"recordings": entries}
    assert entries == [
        {"file": "demo_2.mp4", "title": "Too close", "seconds": 12.5},
        {"file": "demo_1.mp4", "title": "From the left side", "seconds": 12.5},
    ]


def test_a_clip_that_is_not_h264_or_not_the_cameras_size_is_refused(tmp_path: Path) -> None:
    source = write_clip(tmp_path / "small.mp4", (640, 480))

    with pytest.raises(ValueError, match=r"not H\.264"):
        build([(source, "Small")], tmp_path / "out", lambda src, target: shutil.copy(src, target))


@pytest.mark.skipif(
    not (shutil.which("ffmpeg") or shutil.which("avconvert")), reason="no video converter here"
)
def test_a_portrait_clip_comes_out_as_h264_at_its_size(tmp_path: Path) -> None:
    source = write_clip(tmp_path / "portrait.mp4", (1080, 1920))

    entries = build([(source, "Portrait")], tmp_path / "out", converter())

    found = judge_recordings.probe(tmp_path / "out" / "portrait.mp4")
    assert found["codec"] in {"avc1", "h264"} and (found["width"], found["height"]) == (1080, 1920)
    assert entries[0]["file"] == "portrait.mp4"
