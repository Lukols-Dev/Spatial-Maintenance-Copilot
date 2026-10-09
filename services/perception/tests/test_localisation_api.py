"""Localising a viewpoint: the answer, where its truth comes from, and why one is refused."""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smc_core.calibration import load_calibration_record
from smc_core.contracts import Clicks, LandmarkObservation, View, load_clicks
from smc_core.localise import localise
from smc_core.policy import decide
from smc_core.testing import CAMERA_ID, EXTENT_MM, TARGET_ID, clicks_for
from smc_perception.models import LocaliseResult
from workspace_builder import (
    scene_atlas,
    write_atlas,
    write_image,
    write_scene,
    write_viewpoints,
)

REQUEST = {"asset_id": "home-cabinet", "view_set": "cabinet-test", "view": "view_0.png"}
LANDMARK_IDS = [landmark.id for landmark in scene_atlas().landmarks]


@pytest.fixture
def scene(calib: Path) -> Path:
    """The atlas of the synthetic cabinet, and three viewpoints with every point clicked."""
    write_atlas(calib, scene_atlas())
    return write_viewpoints(calib)


def post(client: TestClient, **changes: Any) -> Any:
    return client.post("/localise", json={**REQUEST, **changes})


def read_clicks(folder: Path) -> Any:
    return json.loads((folder / "clicks.json").read_text())


def write_clicks(folder: Path, clicks: Any) -> None:
    (folder / "clicks.json").write_text(json.dumps(clicks))


# ---- the answer ------------------------------------------------------------------


def test_a_viewpoint_is_localised_and_judged(scene: Path, client: TestClient) -> None:
    response = post(client)

    assert response.status_code == 200, response.text
    result = response.json()
    LocaliseResult.model_validate(result)
    assert result["request"] == {
        **REQUEST,
        "truth_view": "view_0.png",
        "samples": 500,
        "seed": 0,
        "sigma_px": 2.0,
    }
    assert result["camera_id"] == CAMERA_ID
    assert result["image"] == {"width": 1080, "height": 1920}
    assert result["localisation"]["failure"] is None
    decision = result["decision"]
    assert (decision["reliable"], decision["action"]) == (True, "ACCEPT")
    assert (decision["reasons"], decision["move_reason"]) == ([], "")
    assert result["ignored_points"] == []


def test_the_answer_is_what_smc_core_makes_of_the_files(scene: Path, client: TestClient) -> None:
    """The service adds no geometry: localise() and decide() on the clicks, in atlas order."""
    atlas = scene_atlas()
    phone = scene.parents[2] / "calib" / "intrinsics" / "phone.yml"
    intrinsics = load_calibration_record(str(phone))["intrinsics"]
    marked = load_clicks(scene / "clicks.json").views["view_1.png"]
    view = View(
        view_id="view_1.png",
        camera_id=CAMERA_ID,
        observations=[
            LandmarkObservation(landmark_id=point, pixel=marked[point], sigma_px=2.0)
            for point in LANDMARK_IDS
        ],
    )
    localisation = localise(atlas, view, intrinsics, samples=300, seed=4)

    response = post(client, view="view_1.png", samples=300, seed=4)

    result = LocaliseResult.model_validate(response.json())
    assert result.localisation == localisation
    assert result.decision == decide(localisation, view, atlas, intrinsics)


def test_the_same_clicks_give_the_same_answer_in_any_order(scene: Path, client: TestClient) -> None:
    """RANSAC and the Monte Carlo draws follow the rows, so the service puts them in atlas order."""
    first = post(client).json()
    clicks = read_clicks(scene)
    clicks["views"]["view_0.png"] = dict(reversed(clicks["views"]["view_0.png"].items()))
    write_clicks(scene, clicks)

    assert post(client).json() == first


def test_the_answer_shows_the_clicks_the_projections_and_the_truth(
    scene: Path, client: TestClient
) -> None:
    marked = read_clicks(scene)["views"]["view_0.png"]

    result = post(client).json()

    errors = result["localisation"]["quality"]["reprojection_px"]
    assert [observation["landmark_id"] for observation in result["observations"]] == LANDMARK_IDS
    for observation in result["observations"]:
        assert observation["pixel"] == marked[observation["landmark_id"]]
        assert observation["inlier"] is True
    assert [projection["landmark_id"] for projection in result["projections"]] == LANDMARK_IDS
    for projection in result["projections"]:
        landmark_id = projection["landmark_id"]
        assert projection["in_frame"] and projection["observed"]
        assert math.dist(projection["pixel"], marked[landmark_id]) == pytest.approx(
            errors[landmark_id]
        )
    centre = result["localisation"]["target"]["centre_px"]
    assert result["truth"] == {
        "source_view": "view_0.png",
        "target_px": marked[TARGET_ID],
        "error_px": pytest.approx(math.dist(centre, marked[TARGET_ID])),
        "inside_95": True,
    }


def test_every_landmark_of_the_atlas_is_projected_clicked_or_not(
    scene: Path, client: TestClient
) -> None:
    clicks = read_clicks(scene)
    del clicks["views"]["view_0.png"]["box_on_top"]
    write_clicks(scene, clicks)

    result = post(client).json()

    projections = {projection["landmark_id"]: projection for projection in result["projections"]}
    unobserved = [point for point, projection in projections.items() if not projection["observed"]]
    observed = [observation["landmark_id"] for observation in result["observations"]]
    assert list(projections) == LANDMARK_IDS
    assert unobserved == ["box_on_top"]
    assert projections["box_on_top"]["in_frame"] is True
    assert "box_on_top" not in observed


def test_points_that_are_not_landmarks_of_the_atlas_are_ignored(
    scene: Path, client: TestClient
) -> None:
    before = post(client).json()
    clicks = read_clicks(scene)
    clicks["points"] += ["sticker", "door_logo"]
    clicks["views"]["view_0.png"] |= {"sticker": [10, 20], "door_logo": [30, 40]}
    write_clicks(scene, clicks)

    after = post(client).json()

    assert after["ignored_points"] == ["sticker", "door_logo"]
    assert after["observations"] == before["observations"]
    assert after["localisation"] == before["localisation"]


# ---- the click sigma -----------------------------------------------------------


def test_the_click_sigma_is_the_requests_else_the_atlas_builds_else_2_px(
    calib: Path, client: TestClient
) -> None:
    """The atlas built by the service, with clicks of 1.5 px; then without its report."""
    measured = client.put(
        "/boards/rig_board_a/measurement",
        json={"square_measured_mm": 25.0, "measurement_uncertainty_mm": 0.25},
    )
    assert measured.status_code == 200
    write_scene(calib)
    built = client.post(
        "/atlases",
        json={
            "asset_id": "home-cabinet",
            "view_set": "cabinet",
            "camera_id": CAMERA_ID,
            "board": "rig_board_a",
            "target_id": TARGET_ID,
            "target_extent_mm": list(EXTENT_MM),
            "click_sigma_px": 1.5,
            "samples": 10,
        },
    )
    assert built.status_code == 201, built.text
    write_viewpoints(calib)

    from_the_build = post(client).json()
    asked = post(client, sigma_px=3.0).json()
    (calib / "data" / "atlas" / "home-cabinet.report.json").unlink()
    without_a_report = post(client).json()

    assert from_the_build["request"]["sigma_px"] == 1.5
    assert asked["request"]["sigma_px"] == 3.0
    assert without_a_report["request"]["sigma_px"] == 2.0

    def pose_only(result: Any) -> float:
        return float(result["localisation"]["uncertainty"]["pose_only"]["semi_major_px"])

    # Used, not only echoed: twice the click error spreads the pose about twice as far.
    assert pose_only(asked) > 1.5 * pose_only(from_the_build)


# ---- the truth -----------------------------------------------------------------


def test_a_view_without_the_target_clicked_has_no_truth(scene: Path, client: TestClient) -> None:
    clicks = read_clicks(scene)
    del clicks["views"]["view_1.png"][TARGET_ID]
    write_clicks(scene, clicks)

    result = post(client, view="view_1.png").json()

    assert result["truth"] is None
    assert result["request"]["truth_view"] is None


def test_the_truth_can_come_from_a_shot_from_the_same_spot(calib: Path, client: TestClient) -> None:
    """Door closed: the landmarks are clicked. Door open, the camera unmoved: the target."""
    write_atlas(calib, scene_atlas())
    marked = clicks_for(1.0, ["view_0.png"]).views["view_0.png"]
    closed = {point: pixel for point, pixel in marked.items() if point != TARGET_ID}
    paired = Clicks(
        camera_id=CAMERA_ID,
        views={"closed.png": closed, "open.png": {TARGET_ID: marked[TARGET_ID]}},
    )
    write_viewpoints(calib, "paired", paired)

    alone = post(client, view_set="paired", view="closed.png").json()
    with_truth = post(client, view_set="paired", view="closed.png", truth_view="open.png").json()

    assert alone["truth"] is None
    assert with_truth["request"]["truth_view"] == "open.png"
    assert with_truth["truth"]["source_view"] == "open.png"
    assert with_truth["truth"]["target_px"] == list(marked[TARGET_ID])
    assert with_truth["truth"]["inside_95"] is True
    assert with_truth["localisation"] == alone["localisation"]
    assert with_truth["decision"] == alone["decision"]


def test_a_truth_view_in_the_request_wins_over_the_views_own_click(
    scene: Path, client: TestClient
) -> None:
    """The target clicked in another viewpoint lies far from where this pose puts it."""
    clicked_there = read_clicks(scene)["views"]["view_1.png"][TARGET_ID]

    truth = post(client, truth_view="view_1.png").json()["truth"]

    assert (truth["source_view"], truth["target_px"]) == ("view_1.png", clicked_there)
    assert truth["error_px"] > 100
    assert truth["inside_95"] is False


# ---- what cannot be localised --------------------------------------------------


def test_a_view_with_too_few_landmarks_fails_and_asks_for_a_step_back(
    scene: Path, client: TestClient
) -> None:
    clicks = read_clicks(scene)
    kept = ["corner_top_left", "corner_top_right", "handle_screw", TARGET_ID]
    clicks["views"]["view_0.png"] = {point: clicks["views"]["view_0.png"][point] for point in kept}
    write_clicks(scene, clicks)

    response = post(client)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["localisation"] == {
        "view_id": "view_0.png",
        "failure": "too_few_correspondences",
        "quality": None,
        "pose": None,
        "target": None,
        "uncertainty": None,
    }
    assert [observation["inlier"] for observation in result["observations"]] == [None] * 3
    assert result["projections"] == []
    assert result["truth"] == {
        "source_view": "view_0.png",
        "target_px": clicks["views"]["view_0.png"][TARGET_ID],
        "error_px": None,
        "inside_95": None,
    }
    decision = result["decision"]
    assert (decision["reliable"], decision["action"]) == (False, "MOVE_BACK")
    assert decision["reasons"] == [
        "localisation failed: too few correspondences",
        "3 landmarks matched, needs ≥ 4",
    ]
    assert decision["move_reason"] == "too few landmarks in view to fit a pose"


def test_landmarks_clicked_on_one_pixel_fail_without_an_error(
    scene: Path, client: TestClient
) -> None:
    clicks = read_clicks(scene)
    clicks["views"]["view_0.png"] = dict.fromkeys(LANDMARK_IDS, (500.0, 900.0))
    write_clicks(scene, clicks)

    response = post(client)

    assert response.status_code == 200, response.text
    assert response.json()["localisation"]["failure"] == "pnp_failed"
    assert response.json()["decision"]["action"] == "MOVE_BACK"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"asset_id": "garage-door"}, "no atlas 'garage-door'"),
        ({"view_set": "garage"}, "no view set named 'garage'"),
        ({"view": "view_7.png"}, "no image 'view_7.png' in view set 'cabinet-test'"),
        ({"truth_view": "view_7.png"}, "no image 'view_7.png' in view set 'cabinet-test'"),
    ],
)
def test_an_unknown_atlas_set_view_or_truth_view_is_not_found(
    scene: Path, client: TestClient, changes: dict[str, str], message: str
) -> None:
    response = post(client, **changes)

    assert response.status_code == 404
    assert response.json()["detail"] == message


def test_a_set_without_clicks_cannot_be_localised(scene: Path, client: TestClient) -> None:
    (scene / "clicks.json").unlink()

    response = post(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "view set 'cabinet-test' has no clicks"


def test_a_view_without_clicks_cannot_be_localised(scene: Path, client: TestClient) -> None:
    write_image(scene / "view_7.png", 1080, 1920)

    response = post(client, view="view_7.png")

    assert response.status_code == 409
    assert response.json()["detail"] == "no clicks in view_7.png of view set 'cabinet-test'"


def test_a_truth_view_without_the_target_clicked_is_refused(
    scene: Path, client: TestClient
) -> None:
    clicks = read_clicks(scene)
    del clicks["views"]["view_1.png"][TARGET_ID]
    write_clicks(scene, clicks)

    response = post(client, truth_view="view_1.png")

    assert response.status_code == 409
    assert response.json()["detail"] == "the target 'drone' is not clicked in view_1.png"


@pytest.mark.parametrize(
    ("camera_id", "message"),
    [
        ("phone-0.5x", "no calibration of camera 'phone-0.5x' in calib/intrinsics"),
        ("", "the clicks of view set 'cabinet-test' name no camera"),
    ],
)
def test_clicks_without_a_calibrated_camera_are_refused(
    scene: Path, client: TestClient, camera_id: str, message: str
) -> None:
    clicks = read_clicks(scene)
    clicks["camera_id"] = camera_id
    write_clicks(scene, clicks)

    response = post(client)

    assert response.status_code == 409
    assert response.json()["detail"] == message


def test_images_of_another_size_than_the_camera_are_refused(
    scene: Path, client: TestClient
) -> None:
    write_viewpoints(scene.parents[2], "landscape", size=(1920, 1080))

    response = post(client, view_set="landscape")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "view_0.png in view set 'landscape' is 1920x1080 px (rotated by 90 degrees), "
        "but phone-1x-portrait was calibrated at 1080x1920 px"
    )


@pytest.mark.parametrize(
    ("file", "text", "message"),
    [
        (
            "data/atlas/home-cabinet.json",
            '{"asset_id": "home-cabinet"}',
            "data/atlas/home-cabinet.json is not an atlas: ",
        ),
        (
            "data/views/cabinet-test/clicks.json",
            '{"camera_id": "", "points": ["a", "a"], "views": {}}',
            "data/views/cabinet-test/clicks.json is not valid: ",
        ),
    ],
)
def test_an_atlas_or_clicks_that_cannot_be_read_are_refused(
    scene: Path, client: TestClient, file: str, text: str, message: str
) -> None:
    (scene.parents[2] / file).write_text(text)

    response = post(client)

    assert response.status_code == 409
    assert response.json()["detail"].startswith(message)


@pytest.mark.parametrize(
    "changes",
    [
        {"samples": 49},
        {"samples": 5001},
        {"seed": -1},
        {"sigma_px": 0},
        {"asset_id": "../home-cabinet"},
        {"view_set": ".hidden"},
        {"view": ""},
        {"view": "clicks.json"},
        {"truth_view": "../outside.png"},
        {"colour": "red"},
    ],
)
def test_an_invalid_request_is_refused(
    scene: Path, client: TestClient, changes: dict[str, Any]
) -> None:
    assert post(client, **changes).status_code == 422


# ---- read-only -------------------------------------------------------------------


def test_a_read_only_service_localises_and_writes_nothing(
    scene: Path, client: TestClient, read_only: None
) -> None:
    root = scene.parents[2]

    def files() -> dict[str, tuple[int, int]]:
        return {
            path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in root.rglob("*")
            if path.is_file()
        }

    before = files()
    response = post(client)

    assert response.status_code == 200, response.text
    assert files() == before
    assert client.post("/atlases", json={}).status_code == 403
