"""The printed markers of a view set, found in every image and saved as its clicks.

The set is the synthetic marked scene of smc_core.testing: eight viewpoints of
the rig board with landmark markers 50 to 55 and the target's tag 70 in front
of it, as gen_markers.py prints them. The tag shows in five of the viewpoints.
"""

import json
from pathlib import Path
from typing import Any

import cv2 as cv
import pytest
from fastapi.testclient import TestClient
from smc_core.testing import CAMERA_ID, MARKERS_MM, rendered_marker_views, rig_board
from smc_perception.models import MarkersAnswer
from workspace_builder import MARKERS_YAML, RIG_YAML, write_calibration, write_rig, write_view_set

SET = "cabinet-markers"


@pytest.fixture(scope="module")
def frames(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    """The rendered frames as PNG, once for the module: rendering is the slow part."""
    encoded = {}
    for name, frame in rendered_marker_views(rig_board(), MARKERS_MM):
        ok, data = cv.imencode(".png", frame)
        assert ok
        encoded[name] = data.tobytes()
    return encoded


@pytest.fixture
def marked(root: Path, frames: dict[str, bytes]) -> Path:
    """The phone's calibration, a rig file with markers, and the set of marked frames."""
    write_calibration(root)
    write_rig(root, RIG_YAML + MARKERS_YAML)
    folder = root / "data" / "views" / SET
    folder.mkdir(parents=True)
    for name, data in frames.items():
        (folder / name).write_bytes(data)
    return folder


def post(client: TestClient, body: dict[str, Any], name: str = SET) -> Any:
    return client.post(f"/view-sets/{name}/markers", json={"camera_id": CAMERA_ID} | body)


def answer_of(response: Any) -> MarkersAnswer:
    assert response.status_code == 200, response.text
    return MarkersAnswer.model_validate(response.json())


def saved(folder: Path) -> Any:
    return json.loads((folder / "clicks.json").read_text())


def test_the_markers_of_every_image_become_the_sets_clicks(
    marked: Path, client: TestClient
) -> None:
    answer = answer_of(post(client, {}))

    assert (answer.view_set, answer.images, answer.marked_images) == (SET, 8, 8)
    assert answer.tag_images == 5
    assert [count.marker_id for count in answer.markers] == list(range(50, 61))
    assert {count.marker_id: count.images for count in answer.markers if count.images} == {
        50: 7,
        51: 7,
        52: 8,
        53: 7,
        54: 8,
        55: 8,
    }
    clicks = saved(marked)
    assert clicks["camera_id"] == CAMERA_ID
    assert clicks["points"][:4] == ["m50_0", "m50_1", "m50_2", "m50_3"]
    assert clicks["points"][-5:] == ["target", "target_0", "target_1", "target_2", "target_3"]
    assert {"m50_0", "target", "target_3"} <= clicks["views"]["view_0.png"].keys()
    assert answer.clicks.marked_images == 8
    assert answer.clicks.point_views["m50_0"] == 7
    assert answer.clicks.point_views["target"] == 5


def test_the_workspace_lists_the_new_points(marked: Path, client: TestClient) -> None:
    answer_of(post(client, {"target_id": "box"}))

    (summary,) = client.get("/workspace").json()["view_sets"]
    assert summary["clicks"]["point_views"]["box"] == 5
    assert summary["clicks"]["camera_id"] == CAMERA_ID


def test_markers_on_a_part_that_opens_are_left_out_where_the_tag_shows(
    marked: Path, client: TestClient
) -> None:
    answer = answer_of(post(client, {"moving": [50, 51]}))

    # Only the three frames without the tag keep them; the others are unchanged.
    counts = {count.marker_id: count.images for count in answer.markers}
    assert (counts[50], counts[51], counts[52]) == (3, 2, 8)
    for points in saved(marked)["views"].values():
        if "target" in points:
            assert not {"m50_0", "m51_0"} & points.keys()


def test_clicks_the_set_has_are_kept_unless_replaced(marked: Path, client: TestClient) -> None:
    (marked / "clicks.json").write_text('{"camera_id": "", "views": {}}')

    refused = post(client, {})

    assert refused.status_code == 409
    assert "has clicks" in refused.json()["detail"]
    assert saved(marked)["camera_id"] == ""
    answer_of(post(client, {"replace": True}))
    assert saved(marked)["camera_id"] == CAMERA_ID


def test_only_landmark_markers_can_move(marked: Path, client: TestClient) -> None:
    response = post(client, {"moving": [70, 99]})

    assert response.status_code == 422
    assert response.json()["detail"] == "moving: 70, 99 are not landmark markers of calib/rig.yaml"
    assert not (marked / "clicks.json").exists()


def test_a_rig_without_markers_is_refused(marked: Path, client: TestClient) -> None:
    write_rig(marked.parents[2])

    response = post(client, {})

    assert response.status_code == 409
    assert "names no printed markers" in response.json()["detail"]


def test_images_of_another_size_than_the_camera_are_refused(
    marked: Path, client: TestClient
) -> None:
    write_view_set(marked.parents[2], "small", {"a.png": (64, 48)})

    response = post(client, {}, name="small")

    assert response.status_code == 409
    assert "was calibrated at" in response.json()["detail"]


def test_a_camera_that_is_not_calibrated_is_not_found(marked: Path, client: TestClient) -> None:
    response = post(client, {"camera_id": "no-such-phone"})

    assert response.status_code == 404


def test_images_without_markers_mark_nothing(root: Path, client: TestClient) -> None:
    write_calibration(root)
    write_rig(root, RIG_YAML + MARKERS_YAML)
    folder = write_view_set(root, "blank", {"a.png": (1080, 1920), "b.png": (1080, 1920)})

    response = post(client, {}, name="blank")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "no marker of calib/rig.yaml in the 2 images of view set 'blank'"
    )
    assert not (folder / "clicks.json").exists()


def test_a_read_only_service_refuses_to_mark(
    marked: Path, client: TestClient, read_only: None
) -> None:
    response = post(client, {})

    assert response.status_code == 403
    assert not (marked / "clicks.json").exists()


# ---- the rig's markers in the workspace ---------------------------------------------


def test_the_workspace_names_the_rigs_markers(marked: Path, client: TestClient) -> None:
    rig = client.get("/workspace").json()["rig"]

    assert rig["markers"] == {"landmark_ids": [50, 60], "target_id": 70, "side_mm": 40.0}
    assert rig["error"] is None


def test_a_rig_without_markers_has_none(calib: Path, client: TestClient) -> None:
    rig = client.get("/workspace").json()["rig"]

    assert rig["markers"] is None
    assert rig["error"] is None


def test_a_broken_markers_section_is_an_error_of_the_rig(calib: Path, client: TestClient) -> None:
    write_rig(calib, RIG_YAML + "markers:\n  landmark_ids: [50, 60]\n")

    rig = client.get("/workspace").json()["rig"]

    assert rig["markers"] is None
    assert rig["error"] == "markers: no target_id"
    assert len(rig["boards"]) == 3
