"""Agent sessions over HTTP: the workspace as the agent sees it, and the answers.

The synthetic cabinet: A is a viewpoint with every landmark in sight, so its
result is reliable; B sees four landmarks and C three, so neither is. A_open
is A's shot with the target in sight, its truth. The tests give the agent no
model, so it speaks with the policy's own words, unless a test gives it one.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smc_agent.model import ModelTurn, NoModel
from smc_core.contracts import Clicks
from smc_core.testing import POINTS_MM, TARGET_ID, clicks_for, scene_atlas
from smc_perception.models import SessionTurn
from workspace_builder import write_atlas, write_view_set

LANDMARKS = [point for point in POINTS_MM if point != TARGET_ID]
START = {"asset_id": "home-cabinet", "view_set": "cabinet-agent"}


@pytest.fixture(autouse=True)
def no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never Bedrock in a test: the model settings are not read at all."""
    monkeypatch.setattr(
        "smc_perception.routes.sessions.agent_model", lambda: NoModel("no model in the tests")
    )
    monkeypatch.setattr("smc_perception.routes.sessions.model_name", lambda: "none in the tests")


@pytest.fixture
def agent_set(calib: Path) -> Path:
    write_atlas(calib, scene_atlas())
    every = clicks_for(1.0).views
    views = {
        "A_close.png": {point: every["view_0.png"][point] for point in LANDMARKS},
        "A_open.png": dict(every["view_0.png"]),
        "B_close.png": {point: every["view_1.png"][point] for point in LANDMARKS[:4]},
        "C_close.png": {point: every["view_2.png"][point] for point in LANDMARKS[:3]},
    }
    clicks = Clicks(camera_id=clicks_for(1.0).camera_id, points=list(POINTS_MM), views=views)
    folder = write_view_set(calib, "cabinet-agent", dict.fromkeys(views, (1080, 1920)))
    (folder / "clicks.json").write_text(clicks.model_dump_json(indent=2))
    return folder


def start(client: TestClient, view: str) -> Any:
    return client.post("/sessions", json={**START, "view": view})


def turn_of(response: Any) -> dict[str, Any]:
    assert response.status_code in (200, 201), response.text
    answer: dict[str, Any] = SessionTurn.model_validate(response.json()).model_dump(mode="json")
    return answer


def kinds(answer: dict[str, Any]) -> list[str]:
    return [event["kind"] for event in answer["turn"]["events"]]


# ---- a session -------------------------------------------------------------------


def test_a_session_starts_at_a_viewpoint_and_asks_for_the_policy_s_move(
    agent_set: Path, client: TestClient
) -> None:
    response = start(client, "B_close.png")

    assert response.status_code == 201
    answer = turn_of(response)
    turn = answer["turn"]
    assert turn["asset_id"] == "home-cabinet" and turn["view_set"] == "cabinet-agent"
    assert turn["located"]["view"] == "B_close.png"
    request = turn["awaiting"]
    assert request["kind"] == "view"
    assert request["action"] == turn["located"]["decision"]["action"] != "ACCEPT"
    assert request["move_reason"] in request["guidance"]
    assert kinds(answer) == ["perception", "decision", "fallback", "agent"]
    assert answer["result"]["request"]["view"] == "B_close.png"
    assert answer["model"] == "none in the tests"


def test_a_reliable_viewpoint_is_shown_against_its_paired_truth(
    agent_set: Path, client: TestClient
) -> None:
    answer = turn_of(start(client, "A_close.png"))

    assert answer["turn"]["awaiting"]["kind"] == "approval"
    assert answer["result"]["request"]["truth_view"] == "A_open.png"
    assert answer["result"]["truth"]["inside_95"] is True


def test_a_whole_session_runs_to_the_operator_s_approval(
    agent_set: Path, client: TestClient
) -> None:
    session_id = turn_of(start(client, "B_close.png"))["turn"]["session_id"]

    chosen = turn_of(client.post(f"/sessions/{session_id}/view", json={"view": "A_close.png"}))
    ended = turn_of(client.post(f"/sessions/{session_id}/approval", json={"approved": True}))

    assert chosen["turn"]["awaiting"]["kind"] == "approval"
    assert kinds(chosen) == ["human", "perception", "decision", "fallback", "agent"]
    assert ended["turn"]["outcome"] == "accepted"
    assert ended["turn"]["awaiting"] is None
    trace = turn_of(client.get(f"/sessions/{session_id}"))["turn"]["events"]
    assert [event["step"] for event in trace] == list(range(1, 11))


def test_a_view_too_poor_to_pose_asks_to_step_back_with_no_suggestion(
    agent_set: Path, client: TestClient
) -> None:
    request = turn_of(start(client, "C_close.png"))["turn"]["awaiting"]

    assert request["action"] == "MOVE_BACK"
    assert request["suggested_views"] == []


def test_suggestions_are_viewpoints_of_the_set(agent_set: Path, client: TestClient) -> None:
    request = turn_of(start(client, "B_close.png"))["turn"]["awaiting"]

    assert set(request["suggested_views"]) <= {"A_close.png", "C_close.png"}


def test_a_read_only_service_runs_sessions(
    agent_set: Path, client: TestClient, read_only: None
) -> None:
    session_id = turn_of(start(client, "B_close.png"))["turn"]["session_id"]

    response = client.post(f"/sessions/{session_id}/view", json={"view": "A_close.png"})

    assert response.status_code == 200


# ---- the model --------------------------------------------------------------------


class AskToStepAside:
    """A model that asks for the policy's own move, in its own words."""

    def respond(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        facts = json.loads(messages[-1]["content"][-1]["text"])
        call = {
            "action": facts["policy_move"],
            "guidance": "Step aside so the marks along the edge come into view.",
            "views": [],
        }
        return ModelTurn(
            content=[{"type": "tool_use", "id": "t1", "name": "request_view", "input": call}],
            stop_reason="tool_use",
        )


def test_the_model_s_words_reach_the_operator(
    agent_set: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("smc_perception.routes.sessions.agent_model", AskToStepAside)

    answer = turn_of(start(client, "B_close.png"))

    assert answer["turn"]["awaiting"]["guidance"] == (
        "Step aside so the marks along the edge come into view."
    )
    assert kinds(answer) == ["perception", "decision", "agent"]


# ---- refusals ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("view", "status"),
    [("A_open.png", 422), ("nowhere.png", 422)],
)
def test_only_viewpoints_with_the_target_hidden_start_a_session(
    agent_set: Path, client: TestClient, view: str, status: int
) -> None:
    response = start(client, view)

    assert response.status_code == status
    assert "is not a viewpoint" in response.json()["detail"]


def test_an_unknown_session_is_404(agent_set: Path, client: TestClient) -> None:
    assert client.get("/sessions/nope").status_code == 404
    assert client.post("/sessions/nope/view", json={"view": "A_close.png"}).status_code == 404


def test_an_answer_the_session_does_not_wait_for_is_409(
    agent_set: Path, client: TestClient
) -> None:
    session_id = turn_of(start(client, "A_close.png"))["turn"]["session_id"]

    response = client.post(f"/sessions/{session_id}/view", json={"view": "B_close.png"})

    assert response.status_code == 409
    assert "not waiting for a view" in response.json()["detail"]


def test_a_session_on_an_unknown_atlas_is_404(agent_set: Path, client: TestClient) -> None:
    response = client.post("/sessions", json={**START, "asset_id": "nope", "view": "B_close.png"})

    assert response.status_code == 404
