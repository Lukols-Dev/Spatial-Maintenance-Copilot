"""Atlases: built from a view set of the synthetic scene, then read back."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from build_atlas import main as build_atlas_cli
from fastapi.testclient import TestClient
from smc_core.contracts import load_atlas
from smc_core.testing import CAMERA_ID, EXTENT_MM, POINTS_MM, TARGET_ID
from smc_perception.models import AtlasDetail
from workspace_builder import write_calibration, write_scene, write_view_set

REQUEST = {
    "asset_id": "home-cabinet",
    "view_set": "cabinet",
    "camera_id": CAMERA_ID,
    "board": "rig_board_a",
    "target_id": TARGET_ID,
    "target_extent_mm": list(EXTENT_MM),
}


@pytest.fixture
def scene(calib: Path, client: TestClient) -> Path:
    """The clicked views of the cabinet, with rig_board_a measured."""
    measured = client.put(
        "/boards/rig_board_a/measurement",
        json={"square_measured_mm": 25.0, "measurement_uncertainty_mm": 0.25},
    )
    assert measured.status_code == 200
    return write_scene(calib)


def build(client: TestClient, **changes: Any) -> Any:
    return client.post("/atlases", json={**REQUEST, **changes})


def test_an_atlas_is_built_from_the_clicked_views(scene: Path, client: TestClient) -> None:
    response = build(client, target_measured_mm=[60, 90, 420])

    assert response.status_code == 201, response.text
    detail = AtlasDetail.model_validate(response.json())
    atlas, report = detail.atlas, detail.report
    assert atlas.asset_id == "home-cabinet"
    assert atlas.frame == "board:rig_board_a"
    assert {landmark.id for landmark in atlas.landmarks} == set(POINTS_MM) - {TARGET_ID}
    for landmark in atlas.landmarks:
        error = np.linalg.norm(np.array(landmark.position_mm) - POINTS_MM[landmark.id])
        assert error < 3 * landmark.sigma_mm * np.sqrt(3), landmark.id
    assert np.linalg.norm(np.array(atlas.target.position_mm) - POINTS_MM[TARGET_ID]) < 10

    assert report is not None
    assert [view.file for view in report.posed_views] == [f"view_{index}.png" for index in range(8)]
    assert all(view.corners == 15 for view in report.posed_views)
    assert report.unposed_views == []
    assert [point.id for point in report.points] == sorted(POINTS_MM)
    target = next(point for point in report.points if point.is_target)
    assert target.id == TARGET_ID
    assert target.sigma_mm == atlas.target.sigma_mm
    assert target.sigma_mm == pytest.approx(np.hypot(target.triangulation_sigma_mm, 5.0))
    assert target.views == 8
    assert report.skipped == {}
    assert report.target_gap_mm is not None and report.target_gap_mm < 10
    assert report.request.samples == 200


def test_the_built_atlas_is_listed_and_read_back(scene: Path, client: TestClient) -> None:
    built = build(client).json()

    assert client.get("/atlases/home-cabinet").json() == built
    (summary,) = client.get("/workspace").json()["atlases"]
    assert summary["asset_id"] == "home-cabinet"
    assert summary["file"] == "home-cabinet.json"
    assert summary["has_report"] is True
    assert summary["built_at"] == built["report"]["built_at"]
    assert summary["landmarks"] == len(POINTS_MM) - 1
    atlas_dir = scene.parents[2] / "data" / "atlas"
    assert sorted(path.name for path in atlas_dir.iterdir()) == [
        "home-cabinet.json",
        "home-cabinet.report.json",
    ]
    assert (atlas_dir / "home-cabinet.json").read_text().endswith("}\n")


def test_the_service_and_the_cli_build_the_same_atlas(
    scene: Path, client: TestClient, tmp_path: Path
) -> None:
    root = scene.parents[2]
    api_atlas = build(client, seed=7, samples=50).json()["atlas"]

    out = tmp_path / "cli.json"
    build_atlas_cli([
        str(scene),
        "--clicks", str(scene / "clicks.json"),
        "--intrinsics", str(root / "calib" / "intrinsics" / "phone.yml"),
        "--rig", str(root / "calib" / "rig.yaml"),
        "--board", "rig_board_a",
        "--asset-id", "home-cabinet",
        "--target-id", TARGET_ID,
        "--target-extent", *(str(value) for value in EXTENT_MM),
        "--click-sigma-px", "2.0",
        "--samples", "50",
        "--seed", "7",
        "--out", str(out),
    ])  # fmt: skip

    assert load_atlas(out).model_dump(mode="json") == api_atlas


def test_a_report_of_an_earlier_build_is_not_shown_with_a_newer_atlas(
    scene: Path, client: TestClient
) -> None:
    build(client)
    atlas_file = scene.parents[2] / "data" / "atlas" / "home-cabinet.json"
    atlas = json.loads(atlas_file.read_text())
    atlas["target"]["position_mm"][0] += 1.0  # as if the CLI had rebuilt it
    atlas_file.write_text(json.dumps(atlas))

    assert client.get("/atlases/home-cabinet").json()["report"] is None
    assert client.get("/workspace").json()["atlases"][0]["has_report"] is False


def test_an_unmeasured_board_cannot_pose_the_views(calib: Path, client: TestClient) -> None:
    write_scene(calib)

    response = build(client)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "board 'rig_board_a' is not measured: square_measured_mm is null"
    )


def test_clicks_made_for_another_camera_are_refused(scene: Path, client: TestClient) -> None:
    clicks = json.loads((scene / "clicks.json").read_text())
    clicks["camera_id"] = "phone-0.5x"
    (scene / "clicks.json").write_text(json.dumps(clicks))

    response = build(client)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "the clicks of view set 'cabinet' name 'phone-0.5x', not 'phone-1x-portrait'"
    )


def test_a_camera_calibrated_in_two_files_is_ambiguous(scene: Path, client: TestClient) -> None:
    write_calibration(scene.parents[2], file="phone-again.yml")

    response = build(client)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "camera 'phone-1x-portrait' is calibrated in several files: phone-again.yml, phone.yml"
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"view_set": "garage"}, "no view set named 'garage'"),
        ({"camera_id": "phone-3x"}, "no calibration of camera 'phone-3x' in calib/intrinsics"),
        ({"board": "rig_board_z"}, "no board named 'rig_board_z' in calib/rig.yaml"),
    ],
)
def test_an_unknown_set_camera_or_board_is_not_found(
    scene: Path, client: TestClient, changes: dict[str, str], message: str
) -> None:
    response = build(client, **changes)

    assert response.status_code == 404
    assert response.json()["detail"] == message


def test_a_set_without_clicks_cannot_be_built(scene: Path, client: TestClient) -> None:
    (scene / "clicks.json").unlink()

    response = build(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "view set 'cabinet' has no clicks"


def test_images_of_another_size_than_the_camera_are_refused(
    scene: Path, client: TestClient
) -> None:
    write_view_set(scene.parents[2], "landscape", {"a.png": (1920, 1080)})
    (scene.parent / "landscape" / "clicks.json").write_text(
        json.dumps({"camera_id": CAMERA_ID, "views": {"a.png": {"drone": [1, 2]}}})
    )

    response = build(client, view_set="landscape")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "the images of view set 'landscape' are 1920x1080 px (rotated by 90 degrees), "
        "but phone-1x-portrait was calibrated at 1080x1920 px"
    )


def test_a_target_that_was_never_clicked_is_reported(scene: Path, client: TestClient) -> None:
    response = build(client, target_id="pump")

    assert response.status_code == 409
    assert response.json()["detail"] == "target 'pump' is not located: never clicked"
    assert not (scene.parents[2] / "data" / "atlas").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"asset_id": "../cabinet"},
        {"asset_id": "cabinet.report"},
        {"view_set": ".hidden"},
        {"samples": 5},
        {"samples": 2001},
        {"target_extent_mm": [300, 0, 100]},
        {"click_sigma_px": 0},
        {"seed": -1},
        {"colour": "red"},
    ],
)
def test_an_invalid_request_is_refused(
    scene: Path, client: TestClient, changes: dict[str, Any]
) -> None:
    assert build(client, **changes).status_code == 422


def test_an_unknown_or_broken_atlas_cannot_be_read(root: Path, client: TestClient) -> None:
    assert client.get("/atlases/cabinet").status_code == 404
    assert client.get("/atlases/%2E%2E").status_code == 422

    (root / "data" / "atlas").mkdir(parents=True)
    (root / "data" / "atlas" / "cabinet.json").write_text('{"asset_id": "cabinet"}')
    response = client.get("/atlases/cabinet")

    assert response.status_code == 409
    assert response.json()["detail"].startswith("data/atlas/cabinet.json is not an atlas:")


def test_a_read_only_service_builds_nothing(
    scene: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMC_READ_ONLY", "1")

    response = build(client)

    assert response.status_code == 403
    assert not (scene.parents[2] / "data" / "atlas").exists()
