"""A scripted model and a perception with fixed answers: the agent's tests run offline.

The perception stands for the service: each viewpoint has its localisation and
the policy's decision on it, as /localise would give them. The model plays a
script of turns, one per call, and records what it was sent, so a test can
check both what the agent did and what it told the model.
"""

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from smc_agent.contracts import Located
from smc_agent.copilot import Copilot
from smc_agent.model import ModelTurn, ModelUnavailable
from smc_core.contracts import Action, Decision, Failure, Localisation, Policy

ASSET, VIEW_SET = "cabinet-manual", "cabinet-manual-test"
FRONT, SIDE, BLIND = "B1_close.png", "B5_close.png", "B6_close.png"
SIDE_REASON = "landmarks side_bottom, side_top face away from the camera, seen from further left"


def located(
    view: str, action: Action, move_reason: str = "", failure: Failure | None = None
) -> Located:
    """A view as the perception reports it: reliable exactly when the action is ACCEPT."""
    reliable = action is Action.ACCEPT
    return Located(
        view=view,
        localisation=Localisation(view_id=view, failure=failure),
        decision=Decision(
            reliable=reliable,
            action=action,
            reasons=[] if reliable else ["4 inliers, needs ≥ 6"],
            move_reason=move_reason,
            checks=[],
            policy=Policy(),
        ),
    )


@dataclass
class FakePerception:
    """The viewpoints of one view set, each with a fixed localisation and decision."""

    views: dict[str, Located] = field(
        default_factory=lambda: {
            FRONT: located(FRONT, Action.MOVE_LEFT, SIDE_REASON),
            SIDE: located(SIDE, Action.ACCEPT),
            BLIND: located(
                BLIND,
                Action.MOVE_BACK,
                "too few landmarks in view to fit a pose",
                Failure.TOO_FEW_CORRESPONDENCES,
            ),
        }
    )
    suggestions: dict[tuple[str, Action], list[str]] = field(
        default_factory=lambda: {(FRONT, Action.MOVE_LEFT): [SIDE, "B7_close.png"]}
    )
    localised: list[str] = field(default_factory=list)
    suggested: list[tuple[str, Action]] = field(default_factory=list)

    def localise(self, view: str) -> Located:
        self.localised.append(view)
        return self.views[view]

    def viewpoints(self) -> list[str]:
        return [*self.views, "B7_close.png"]

    def suggest(self, view: str, action: Action) -> list[str]:
        self.suggested.append((view, action))
        return self.suggestions.get((view, action), [])


@dataclass
class Call:
    system: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]

    @property
    def tool_names(self) -> set[str]:
        return {tool["name"] for tool in self.tools}


Step = ModelTurn | Exception | Callable[[Call], ModelTurn]


@dataclass
class ScriptedModel:
    """Answers each call with the next step of the script; an exception is raised."""

    script: list[Step] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)

    def respond(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        call = Call(system, copy.deepcopy(messages), copy.deepcopy(tools))
        self.calls.append(call)
        if not self.script:
            raise AssertionError(f"the model was called {len(self.calls)} times, beyond its script")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(call)
        return step


def tool_use(name: str, tool_input: dict[str, Any], call_id: str = "call_1") -> ModelTurn:
    """A model turn that calls one tool, the way the API returns it."""
    return ModelTurn(
        content=[
            {"type": "text", "text": "Checking the localisation."},
            {"type": "tool_use", "id": call_id, "name": name, "input": tool_input},
        ],
        stop_reason="tool_use",
    )


def ask_left(views: list[str] | None = None, call_id: str = "call_1") -> ModelTurn:
    return tool_use(
        "request_view",
        {
            "action": "MOVE_LEFT",
            "guidance": "Move the camera to the left so the marks on the side come into view.",
            "views": [SIDE] if views is None else views,
        },
        call_id,
    )


def present(call_id: str = "call_2") -> ModelTurn:
    return tool_use(
        "present_result",
        {
            "explanation": "The box sits behind the lower part of the flap, inside the region shown.",
            "next_step": "Open the flap and reach to the box behind its lower edge.",
        },
        call_id,
    )


UNAVAILABLE = ModelUnavailable("Bedrock did not answer")


def copilot_for(
    model: ScriptedModel,
    perception: FakePerception,
    saver: InMemorySaver,
    opened: list[tuple[str, str]] | None = None,
) -> Copilot:
    def perception_for(asset_id: str, view_set: str) -> FakePerception:
        if opened is not None:
            opened.append((asset_id, view_set))
        return perception

    return Copilot(model=model, perception_for=perception_for, checkpointer=saver)
