"""Freezing a dataset from a workspace, and reading it back only when nothing has changed."""

import json
import re
from pathlib import Path

import cv2 as cv
import numpy as np
import pytest
from eval_scene import ACCEPTED, BUILD, TEST, TEST_FRAMES, write_workspace
from smc_core.testing import VIEWPOINTS, camera_pose, scene_atlas
from smc_core.viewpoints import camera_centre
from smc_eval.dataset import (
    DatasetError,
    Manifest,
    check_media,
    freeze,
    load_dataset,
    sha256_of,
    videos_in,
)

FROZEN_AT = "2026-10-14T12:00:00+02:00"


def frozen(root: Path, name: str = "cabinet-test") -> tuple[Path, Manifest]:
    paths = write_workspace(root)
    out = root / "eval" / "datasets" / name
    manifest = freeze(
        out,
        name=name,
        root=root,
        atlas_file=paths["atlas"],
        camera_file=paths["camera"],
        rig_file=root / "calib" / "rig.yaml",
        videos=videos_in(paths["videos"]),
        sets=[(paths["test"], "test"), (paths["build"], "build")],
        frozen_at=FROZEN_AT,
        git_commit="abc123",
    )
    return out, manifest


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, Manifest]:
    """One frozen workspace for the tests that only read it."""
    root = tmp_path_factory.mktemp("workspace")
    out, manifest = frozen(root)
    return root, out, manifest


def test_the_manifest_names_every_source_by_its_hash(
    workspace: tuple[Path, Path, Manifest],
) -> None:
    root, _, manifest = workspace

    assert (manifest.asset_id, manifest.board, manifest.camera_id) == (
        "home-cabinet",
        "rig_board_a",
        "phone-1x-portrait",
    )
    assert [video.path for video in manifest.videos] == ["data/recordings/B/B1_close.MOV"]
    assert [(view_set.name, view_set.role) for view_set in manifest.sets] == [
        (TEST, "test"),
        (BUILD, "build"),
    ]
    frames = manifest.sets[0].frames
    assert sorted(frame.path.rsplit("/", 1)[-1] for frame in frames) == sorted(TEST_FRAMES)
    assert {frame.size_px for frame in frames} == {(1080, 1920)}
    assert frames[0].sha256 == sha256_of(root / frames[0].path)
    assert manifest.camera.path == "calib/intrinsics/phone.yml"


def test_the_folder_holds_what_the_evaluation_reads(
    workspace: tuple[Path, Path, Manifest],
) -> None:
    _, out, manifest = workspace

    assert sorted(manifest.files) == [
        "atlas.json",
        "atlas.report.json",
        f"sets/{BUILD}/board_poses.json",
        f"sets/{BUILD}/clicks.json",
        f"sets/{TEST}/board_poses.json",
        f"sets/{TEST}/clicks.json",
    ]
    assert sorted(path.name for path in out.iterdir()) == [
        "atlas.json",
        "atlas.report.json",
        "manifest.json",
        "sets",
    ]


def test_a_frozen_dataset_reads_back_as_it_was(workspace: tuple[Path, Path, Manifest]) -> None:
    root, out, _ = workspace

    dataset = load_dataset(out, root)

    assert dataset.name == "cabinet-test"
    assert dataset.atlas == scene_atlas()
    assert dataset.sigma_px == 1.0
    assert dataset.sets[TEST].role == "test" and dataset.with_role("build")[0].name == BUILD
    assert dataset.manifest_sha256 == sha256_of(out / "manifest.json")


def test_the_board_puts_the_camera_where_it_stood(workspace: tuple[Path, Path, Manifest]) -> None:
    root, out, _ = workspace

    poses = load_dataset(out, root).sets[TEST].board_poses

    assert sorted(poses) == sorted(TEST_FRAMES)
    rotation, tvec = camera_pose(*VIEWPOINTS[TEST_FRAMES[ACCEPTED]])
    np.testing.assert_allclose(camera_centre(poses[ACCEPTED].pose), -rotation.T @ tvec, atol=5.0)


def test_a_changed_file_stops_the_reading(tmp_path: Path) -> None:
    out, _ = frozen(tmp_path)
    clicks = out / "sets" / TEST / "clicks.json"
    clicks.write_text(clicks.read_text().replace("A_open", "A_opened"))

    with pytest.raises(DatasetError, match=re.escape(f"sets/{TEST}/clicks.json has changed")):
        load_dataset(out, tmp_path)


def test_a_recalibrated_camera_stops_the_reading(tmp_path: Path) -> None:
    out, _ = frozen(tmp_path)
    camera = tmp_path / "calib" / "intrinsics" / "phone.yml"
    camera.write_text(camera.read_text() + "\n")

    with pytest.raises(DatasetError, match=re.escape("phone.yml has changed since the freeze")):
        load_dataset(out, tmp_path)


def test_a_folder_without_a_manifest_is_no_dataset(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="not a frozen dataset"):
        load_dataset(tmp_path, tmp_path)


def test_a_frozen_dataset_is_never_frozen_over(tmp_path: Path) -> None:
    frozen(tmp_path)

    with pytest.raises(DatasetError, match="is not changed"):
        freeze(
            tmp_path / "eval" / "datasets" / "cabinet-test",
            name="cabinet-test",
            root=tmp_path,
            atlas_file=tmp_path / "data" / "atlas" / "home-cabinet.json",
            camera_file=tmp_path / "calib" / "intrinsics" / "phone.yml",
            rig_file=tmp_path / "calib" / "rig.yaml",
            videos=[],
            sets=[],
            frozen_at=FROZEN_AT,
            git_commit=None,
        )


def freeze_into(root: Path, paths: dict[str, Path], **change: object) -> Manifest:
    arguments: dict[str, object] = {
        "name": "again",
        "root": root,
        "atlas_file": paths["atlas"],
        "camera_file": paths["camera"],
        "rig_file": root / "calib" / "rig.yaml",
        "videos": [],
        "sets": [(paths["test"], "test")],
        "frozen_at": FROZEN_AT,
        "git_commit": None,
    }
    return freeze(root / "eval" / "again", **{**arguments, **change})  # type: ignore[arg-type]


def test_a_frame_of_another_size_cannot_be_frozen(tmp_path: Path) -> None:
    paths = write_workspace(tmp_path)
    cv.imwrite(str(paths["test"] / ACCEPTED), np.zeros((1080, 1920, 3), np.uint8))

    with pytest.raises(DatasetError, match=re.escape("A_close.png is 1920x1080 px")):
        freeze_into(tmp_path, paths)


def test_clicks_of_a_frame_that_is_not_there_cannot_be_frozen(tmp_path: Path) -> None:
    paths = write_workspace(tmp_path)
    (paths["test"] / ACCEPTED).unlink()

    with pytest.raises(DatasetError, match="clicks of frames that are not there"):
        freeze_into(tmp_path, paths)


def test_an_atlas_without_its_build_report_cannot_be_frozen(tmp_path: Path) -> None:
    paths = write_workspace(tmp_path)
    paths["atlas"].with_name("home-cabinet.report.json").unlink()

    with pytest.raises(DatasetError, match="the click sigma comes from the build report"):
        freeze_into(tmp_path, paths)


def test_a_dataset_needs_a_test_set(tmp_path: Path) -> None:
    paths = write_workspace(tmp_path)

    with pytest.raises(DatasetError, match="no test set"):
        freeze_into(tmp_path, paths, sets=[(paths["build"], "build")])


def test_the_media_are_checked_against_the_manifest(tmp_path: Path) -> None:
    _, manifest = frozen(tmp_path)
    assert check_media(manifest, tmp_path) == []

    (tmp_path / "data" / "recordings" / "B" / "B1_close.MOV").unlink()
    (tmp_path / "data" / "views" / TEST / ACCEPTED).write_bytes(b"other pixels")

    assert check_media(manifest, tmp_path) == [
        "data/recordings/B/B1_close.MOV is missing",
        f"data/views/{TEST}/{ACCEPTED} has changed since the freeze",
    ]


def test_the_manifest_is_json_a_reader_can_follow(workspace: tuple[Path, Path, Manifest]) -> None:
    _, out, manifest = workspace

    stored = json.loads((out / "manifest.json").read_text())

    assert stored["frozen_at"] == FROZEN_AT and stored["git_commit"] == "abc123"
    assert Manifest.model_validate(stored) == manifest
