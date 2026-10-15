"""Frames over HTTP: localised from their printed markers, run by the agent, and looked at again.

The workspace is the synthetic marked scene: the marker atlas of smc_core.testing,
whose door hides the target's box, and frames rendered from its viewpoints. The
agent has no model, and the vision model is a fake, so nothing reaches AWS.
"""

from pathlib import Path
from typing import Any

import cv2 as cv
import numpy as np
import pytest
from fastapi.testclient import TestClient
from smc_agent.model import ModelUnavailable, NoModel
from smc_core.testing import (
    CAMERA_ID,
    MARKERS_MM,
    TAG_ID,
    VIEWPOINTS,
    camera_pose,
    marker_atlas,
    render,
    render_markers,
    rig_board,
)
from smc_perception.live import STORE
from smc_perception.models import FrameAnswer, InspectAnswer
from workspace_builder import RIG_YAML, write_atlas, write_calibration, write_rig

MARKERS_SECTION = """\
markers:
  landmark_ids: [50, 60]
  target_id: 70
  side_nominal_mm: 40.0
  side_measured_mm: null
"""
WITHOUT_TAG = {marker: corners for marker, corners in MARKERS_MM.items() if marker != TAG_ID}


@pytest.fixture(autouse=True)
def fresh_store() -> None:
    STORE.clear()


@pytest.fixture(autouse=True)
def no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "smc_perception.routes.sessions.agent_model", lambda: NoModel("no model in the tests")
    )
    monkeypatch.setattr("smc_perception.routes.sessions.model_name", lambda: "none in the tests")
    monkeypatch.setattr("smc_perception.routes.frames.model_name", lambda: "fake in the tests")


@pytest.fixture
def marked(root: Path) -> Path:
    write_calibration(root)
    write_rig(root, RIG_YAML + MARKERS_SECTION)
    write_atlas(root, marker_atlas())
    return root


def png(index: int, placed: dict[int, np.ndarray]) -> bytes:
    rotation, tvec = camera_pose(*VIEWPOINTS[index])
    frame = render_markers(render(rig_board(), rotation, tvec), placed, rotation, tvec)
    ok, encoded = cv.imencode(".png", frame)
    assert ok
    return encoded.tobytes()


def post(client: TestClient, data: bytes, **params: Any) -> Any:
    query = {"asset_id": "home-cabinet", "camera_id": CAMERA_ID, "samples": 100} | params
    return client.post("/frames", params=query, content=data, headers={"Content-Type": "image/png"})


def answer_of(response: Any) -> FrameAnswer:
    assert response.status_code == 201, response.text
    return FrameAnswer.model_validate(response.json())


# ---- a frame ------------------------------------------------------------------------


def test_a_frame_is_localised_from_its_markers(marked: Path, client: TestClient) -> None:
    answer = answer_of(post(client, png(0, WITHOUT_TAG)))

    assert len(answer.observations) == 4 * len(WITHOUT_TAG)
    assert all(observation.inlier for observation in answer.observations)
    assert answer.decision.action == "ACCEPT"
    assert answer.localisation.occluder is not None
    assert answer.localisation.occluder.panel_id == "door"
    assert answer.guidance is not None and answer.guidance.progress is not None
    assert answer.sighting is None
    assert (answer.image.width, answer.image.height) == (1080, 1920)
    assert len(answer.frame_id) == 12


def test_an_open_frame_is_held_against_the_target_s_tag(marked: Path, client: TestClient) -> None:
    answer = answer_of(post(client, png(0, MARKERS_MM)))

    assert answer.sighting is not None and answer.sighting.inside_95 is True
    assert not any(
        observation.landmark_id.startswith("m50_") for observation in answer.observations
    )


@pytest.mark.parametrize(
    ("data", "params", "status", "detail"),
    [
        (b"not an image", {}, 422, "not a JPEG or PNG"),
        (None, {"asset_id": "nope"}, 404, "no atlas"),
        (None, {"camera_id": "nope"}, 404, "no calibration"),
    ],
)
def test_a_frame_that_cannot_be_localised_says_why(
    marked: Path,
    client: TestClient,
    data: bytes | None,
    params: dict[str, str],
    status: int,
    detail: str,
) -> None:
    response = post(client, data if data is not None else png(0, WITHOUT_TAG), **params)

    assert response.status_code == status
    assert detail in response.json()["detail"]


def test_a_frame_of_another_size_is_refused(marked: Path, client: TestClient) -> None:
    ok, encoded = cv.imencode(".png", np.full((1080, 1920, 3), 255, np.uint8))
    assert ok

    response = post(client, encoded.tobytes())

    assert response.status_code == 409


def test_without_printed_markers_in_the_rig_file_frames_are_refused(
    root: Path, client: TestClient
) -> None:
    write_calibration(root)
    write_rig(root)
    write_atlas(root, marker_atlas())

    response = post(client, png(0, WITHOUT_TAG))

    assert response.status_code == 409
    assert "names no printed markers" in response.json()["detail"]


def test_a_read_only_service_localises_frames(
    marked: Path, client: TestClient, read_only: None
) -> None:
    assert post(client, png(0, WITHOUT_TAG)).status_code == 201


# ---- the agent on frames -------------------------------------------------------------


def test_the_agent_runs_on_posted_frames(marked: Path, client: TestClient) -> None:
    first = answer_of(post(client, png(4, WITHOUT_TAG)))
    second = answer_of(post(client, png(0, WITHOUT_TAG)))

    started = client.post(
        "/sessions", json={"asset_id": "home-cabinet", "view_set": "live", "view": first.frame_id}
    )
    assert started.status_code == 201, started.text
    session = started.json()
    assert session["result"] is None
    assert session["turn"]["located"]["view"] == first.frame_id
    if session["turn"]["awaiting"]["kind"] == "view":
        assert session["turn"]["awaiting"]["suggested_views"] == []
        moved = client.post(
            f"/sessions/{session['turn']['session_id']}/view", json={"view": second.frame_id}
        )
        assert moved.status_code == 200, moved.text
        session = moved.json()
    assert session["turn"]["awaiting"]["kind"] == "approval"


def test_a_frame_never_posted_is_no_viewpoint(marked: Path, client: TestClient) -> None:
    response = client.post(
        "/sessions", json={"asset_id": "home-cabinet", "view_set": "live", "view": "abc"}
    )

    assert response.status_code == 422


def test_no_view_set_can_take_the_camera_s_name(calib: Path, client: TestClient) -> None:
    _, encoded = cv.imencode(".png", np.full((1920, 1080, 3), 128, np.uint8))
    response = client.post(
        "/view-sets",
        data={"name": "live"},
        files=[("files", ("a.png", encoded.tobytes(), "image/png"))],
    )

    assert response.status_code == 422
    assert "names the frames of a camera" in response.json()["detail"]


# ---- a second look -------------------------------------------------------------------


class FakeVision:
    def __init__(self, answer: str = "Yes. A box stands behind the door.") -> None:
        self.answer = answer
        self.seen: list[tuple[bytes, str]] = []

    def look(self, image: bytes, image_format: str, question: str) -> str:
        self.seen.append((image, question))
        if not self.answer:
            raise ModelUnavailable("throttled")
        return self.answer


def test_the_target_s_region_is_shown_to_the_vision_model(
    marked: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    vision = FakeVision()
    monkeypatch.setattr("smc_perception.routes.frames.vision_model", lambda: vision)
    frame = answer_of(post(client, png(0, MARKERS_MM)))

    response = client.post(f"/frames/{frame.frame_id}/inspect", json={})

    assert response.status_code == 200, response.text
    answer = InspectAnswer.model_validate(response.json())
    assert (answer.verdict, answer.model) == ("yes", "fake in the tests")
    assert answer.question == "Is the hidden component visible in this region?"
    left, top, right, bottom = answer.region_px
    assert 0 <= left < right <= 1080 and 0 <= top < bottom <= 1920
    assert right - left < 1080
    assert cv.imdecode(np.frombuffer(vision.seen[0][0], np.uint8), cv.IMREAD_COLOR).shape[:2] == (
        bottom - top,
        right - left,
    )


def test_a_vision_model_without_an_answer_is_503(
    marked: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("smc_perception.routes.frames.vision_model", lambda: FakeVision(""))
    frame = answer_of(post(client, png(0, WITHOUT_TAG)))

    response = client.post(f"/frames/{frame.frame_id}/inspect", json={"question": "A box?"})

    assert response.status_code == 503
    assert response.json()["detail"] == "the vision model gave no answer"


def test_an_unknown_frame_cannot_be_inspected(marked: Path, client: TestClient) -> None:
    assert client.post("/frames/nope/inspect", json={}).status_code == 404
