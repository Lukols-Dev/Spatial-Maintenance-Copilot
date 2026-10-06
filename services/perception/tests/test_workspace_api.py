"""GET /workspace: everything on disk, never failing because one file is bad."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from smc_core.testing import CAMERA_ID
from smc_perception.models import Workspace
from smc_perception.settings import workspace_root
from workspace_builder import write_image, write_rig, write_view_set


def get_workspace(client: TestClient) -> Workspace:
    response = client.get("/workspace")
    assert response.status_code == 200, response.text
    return Workspace.model_validate(response.json())


def test_an_empty_workspace_says_what_is_missing(client: TestClient) -> None:
    workspace = get_workspace(client)

    assert workspace.read_only is False
    assert workspace.cameras == []
    assert workspace.rig.boards == []
    assert workspace.rig.error == "calib/rig.yaml not found"
    assert workspace.view_sets == []
    assert workspace.atlases == []


def test_the_workspace_defaults_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SMC_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)

    assert workspace_root() == tmp_path.resolve()


@pytest.mark.parametrize("value", ["1", "true", "YES", " yes "])
def test_read_only_is_reported(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SMC_READ_ONLY", value)

    assert get_workspace(client).read_only is True


def test_a_calibration_is_listed_with_its_numbers(calib: Path, client: TestClient) -> None:
    (camera,) = get_workspace(client).cameras

    assert camera.file == "phone.yml"
    assert camera.camera_id == CAMERA_ID
    assert (camera.image_width, camera.image_height) == (1080, 1920)
    assert camera.frames == 1
    assert camera.rms_px == pytest.approx(0.3)
    assert (camera.fx, camera.fy, camera.cx, camera.cy) == (1675.0, 1677.4, 531.6, 956.2)
    assert camera.dist_coeffs == [0.0] * 5
    assert list(camera.std) == ["fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2", "k3"]
    assert camera.calibrated_at is not None and camera.opencv_version is not None
    assert camera.error is None


def test_a_broken_calibration_is_listed_with_its_error(calib: Path, client: TestClient) -> None:
    (calib / "calib" / "intrinsics" / "broken.yml").write_text("camera_id: [1, 2\n  x: {")
    (calib / "calib" / "intrinsics" / "partial.yml").write_text("%YAML:1.0\n---\ncamera_id: x\n")

    response = client.get("/workspace")
    broken, partial, phone = Workspace.model_validate(response.json()).cameras

    assert broken.error == "cannot parse calibration: calib/intrinsics/broken.yml"
    assert (broken.camera_id, broken.dist_coeffs, broken.std) == (None, [], {})
    assert partial.error is not None and "has no image_width" in partial.error
    assert phone.error is None
    assert str(calib) not in response.text


def test_the_rig_boards_are_listed(calib: Path, client: TestClient) -> None:
    rig = get_workspace(client).rig

    assert rig.dictionary == "DICT_5X5_100"
    assert rig.error is None
    calibration_board, board_a, _ = rig.boards
    assert calibration_board.measured is True
    assert calibration_board.measured_on is not None
    assert calibration_board.measured_on.isoformat() == "2026-09-17"
    assert calibration_board.substrate == "A4 print taped with masking tape to paperboard"
    assert board_a.id == "rig_board_a"
    assert board_a.marker_ids == (20, 31)
    assert board_a.measured is False


def test_a_rig_file_that_is_not_yaml_is_reported(root: Path, client: TestClient) -> None:
    write_rig(root, "boards:\n  a: [1, 2\n")

    rig = get_workspace(client).rig

    assert rig.boards == []
    assert rig.error is not None and rig.error.startswith("cannot read calib/rig.yaml:")


def test_a_broken_board_leaves_the_others_listed(root: Path, client: TestClient) -> None:
    write_rig(root, "dictionary: DICT_5X5_100\nboards:\n  bad:\n    squares_x: 4\n  good:\n"
              "    squares_x: 4\n    squares_y: 6\n    ids: [20, 31]\n    square_nominal_mm: 25.0\n"
              "    marker_nominal_mm: 18.0\n")  # fmt: skip

    rig = get_workspace(client).rig

    assert [board.id for board in rig.boards] == ["good"]
    assert rig.error == "board bad: no ids"


def test_a_view_set_reports_its_images_and_matching_cameras(
    calib: Path, client: TestClient
) -> None:
    write_view_set(calib, "cabinet", {"b.png": (1080, 1920), "a.png": (1080, 1920)})

    (view_set,) = get_workspace(client).view_sets

    assert view_set.name == "cabinet"
    assert (view_set.image_count, view_set.jpeg_count) == (2, 0)
    assert view_set.image_size == (1080, 1920)
    assert view_set.mixed_sizes is False
    assert view_set.camera_ids == [CAMERA_ID]
    assert view_set.clicks is None
    assert view_set.error is None


def test_mixed_image_sizes_match_no_camera(calib: Path, client: TestClient) -> None:
    write_view_set(calib, "mixed", {"a.png": (1080, 1920), "b.png": (1920, 1080)})

    (view_set,) = get_workspace(client).view_sets

    assert view_set.image_size is None
    assert view_set.mixed_sizes is True
    assert view_set.camera_ids == []


def test_a_jpeg_is_counted_and_sized_in_its_sensor_grid(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "photos", {"a.png": (40, 30)})
    write_image(folder / "IMG_1.JPG", 40, 30, exif=True)

    (view_set,) = get_workspace(client).view_sets

    assert (view_set.image_count, view_set.jpeg_count) == (2, 1)
    assert view_set.image_size == (40, 30)


def test_an_unreadable_image_is_named_in_the_set_error(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    (folder / "b.png").write_bytes(b"not a png")

    (view_set,) = get_workspace(client).view_sets

    assert view_set.image_count == 2
    assert view_set.image_size == (40, 30)
    assert view_set.error == "b.png: not a PNG file"


def test_clicks_are_summarised_in_the_annotators_order(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30), "b.png": (40, 30)})
    clicks = {
        "camera_id": CAMERA_ID,
        "points": ["hinge", "drone", "unclicked"],
        "views": {"a.png": {"hinge": [1, 2], "drone": [3, 4]}, "b.png": {"drone": [5, 6]}},
    }
    (folder / "clicks.json").write_text(json.dumps(clicks))

    summary = get_workspace(client).view_sets[0].clicks

    assert summary is not None
    assert summary.camera_id == CAMERA_ID
    assert summary.point_views == {"hinge": 1, "drone": 2, "unclicked": 0}
    assert list(summary.point_views) == ["hinge", "drone", "unclicked"]
    assert (summary.point_count, summary.marked_images, summary.ready_points) == (3, 2, 1)
    assert summary.error is None


def test_clicks_of_an_old_file_count_every_clicked_point(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    (folder / "clicks.json").write_text(
        '{"camera_id": "", "views": {"a.png": {"z": [1, 2], "a": [3, 4]}}}'
    )

    summary = get_workspace(client).view_sets[0].clicks

    assert summary is not None
    assert list(summary.point_views) == ["a", "z"]
    assert summary.point_count == 2


def test_an_invalid_clicks_file_is_reported(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    (folder / "clicks.json").write_text('{"camera_id": "x", "views": {"a.png": {"p": "nowhere"}}}')

    response = client.get("/workspace")
    view_set = Workspace.model_validate(response.json()).view_sets[0]

    assert view_set.error is None
    assert view_set.clicks is not None
    assert view_set.clicks.error is not None
    assert view_set.clicks.error.startswith(
        "data/views/cabinet/clicks.json is not valid: views.a.png.p"
    )
    assert (view_set.clicks.point_count, view_set.clicks.point_views) == (0, {})
    assert str(calib) not in response.text


def test_only_valid_names_are_listed(calib: Path, client: TestClient) -> None:
    folder = write_view_set(calib, "cabinet", {"a.png": (40, 30)})
    (folder / "notes.txt").write_text("not an image")
    write_image(folder / ".hidden.png", 40, 30)
    write_image(folder / "photo (1).png", 40, 30)
    write_view_set(calib, ".import-1234", {"a.png": (40, 30)})
    write_view_set(calib, "with space", {"a.png": (40, 30)})
    write_image(calib / "data" / "views" / "loose.png", 40, 30)

    (view_set,) = get_workspace(client).view_sets

    assert view_set.name == "cabinet"
    assert view_set.image_count == 1


def test_a_set_that_leads_outside_the_workspace_is_not_listed(
    calib: Path, client: TestClient, tmp_path: Path
) -> None:
    outside = write_view_set(tmp_path / "elsewhere", "escape", {"a.png": (40, 30)})
    (calib / "data" / "views").mkdir(parents=True)
    os.symlink(outside, calib / "data" / "views" / "escape")
    write_view_set(calib, "inside", {"a.png": (40, 30)})
    os.symlink(calib / "data" / "views" / "inside", calib / "data" / "views" / "alias")

    names = [view_set.name for view_set in get_workspace(client).view_sets]

    assert names == ["alias", "inside"]


def test_atlases_are_listed_with_broken_ones_marked(calib: Path, client: TestClient) -> None:
    atlas_dir = calib / "data" / "atlas"
    atlas_dir.mkdir(parents=True)
    atlas = {
        "asset_id": "cabinet",
        "version": "2",
        "frame": "board:rig_board_a",
        "landmarks": [{"id": "hinge", "position_mm": [1, 2, 3], "sigma_mm": 1.5}],
        "target": {
            "id": "drone",
            "position_mm": [4, 5, 6],
            "sigma_mm": 5.2,
            "extent_mm": [3, 3, 1],
        },
    }
    (atlas_dir / "cabinet.json").write_text(json.dumps(atlas))
    (atlas_dir / "broken.json").write_text("{")
    (atlas_dir / "cabinet.report.json").write_text("{}")  # not an atlas, never listed

    broken, cabinet = get_workspace(client).atlases

    assert (cabinet.asset_id, cabinet.file, cabinet.version) == ("cabinet", "cabinet.json", "2")
    assert (cabinet.landmarks, cabinet.target_id, cabinet.target_sigma_mm) == (1, "drone", 5.2)
    assert cabinet.has_report is False
    assert cabinet.error is None
    assert broken.asset_id == "broken"
    assert broken.error is not None and broken.error.startswith(
        "data/atlas/broken.json is not an atlas"
    )
    assert broken.landmarks is None
