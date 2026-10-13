"""The agent's loop: perception, the policy's decision, the model's words, the operator.

The policy decides and the model speaks. Every test checks one side of that
line: what the operator is asked, what the trace records, what the model is
sent, and what happens when the model is wrong, refuses or does not answer.
"""

import json
import re

import pytest
from agent_scene import (
    ASSET,
    BLIND,
    FRONT,
    SIDE,
    SIDE_REASON,
    UNAVAILABLE,
    VIEW_SET,
    FakePerception,
    ScriptedModel,
    Step,
    ask_left,
    copilot_for,
    present,
    tool_use,
)
from langgraph.checkpoint.memory import InMemorySaver
from smc_agent.contracts import ApprovalRequest, Turn, ViewRequest
from smc_agent.copilot import MAX_MODEL_CALLS
from smc_agent.model import ModelTurn
from smc_core.contracts import Action

LEFT_GUIDANCE = "Move the camera to the left so the marks on the side come into view."


def kinds(turn: Turn) -> list[str]:
    return [event.kind for event in turn.events]


def checks(turn: Turn) -> list[str]:
    return [event.data["check"] for event in turn.events if event.kind == "guard"]


def view_request(turn: Turn) -> ViewRequest:
    assert isinstance(turn.awaiting, ViewRequest), turn.awaiting
    return turn.awaiting


def approval_request(turn: Turn) -> ApprovalRequest:
    assert isinstance(turn.awaiting, ApprovalRequest), turn.awaiting
    return turn.awaiting


# ---- the loop ----------------------------------------------------------------------


def test_an_unreliable_view_asks_the_operator_for_the_move_the_policy_chose(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    turn = copilot_for(ScriptedModel([ask_left()]), perception, saver).start(
        "s1", ASSET, VIEW_SET, FRONT
    )

    assert turn.session_id == "s1"
    assert turn.located == perception.views[FRONT]
    assert turn.outcome is None
    assert turn.awaiting == ViewRequest(
        view=FRONT,
        action=Action.MOVE_LEFT,
        move_reason=SIDE_REASON,
        guidance=LEFT_GUIDANCE,
        suggested_views=[SIDE],
    )


def test_a_turn_traces_perception_then_the_decision_then_the_agent(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    turn = copilot_for(ScriptedModel([ask_left()]), perception, saver).start(
        "s1", ASSET, VIEW_SET, FRONT
    )

    assert kinds(turn) == ["perception", "decision", "agent"]
    assert [event.node for event in turn.events] == ["localise", "localise", "guide"]
    assert [event.step for event in turn.events] == [1, 2, 3]
    assert turn.events[0].data["view"] == FRONT
    assert turn.events[1].data["action"] == "MOVE_LEFT"


def test_the_perception_is_the_one_of_the_session(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    opened: list[tuple[str, str]] = []

    copilot_for(ScriptedModel([ask_left()]), perception, saver, opened).start(
        "s1", ASSET, VIEW_SET, FRONT
    )

    assert set(opened) == {(ASSET, VIEW_SET)}
    assert perception.localised == [FRONT]


def test_the_model_is_told_the_decision_and_offered_the_tools_of_its_branch(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel([ask_left()])

    copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    call = model.calls[0]
    assert call.tool_names == {"suggest_viewpoints", "request_view"}
    sent = json.dumps(call.messages, ensure_ascii=False)
    assert "MOVE_LEFT" in sent
    assert SIDE_REASON in sent
    assert "4 inliers, needs ≥ 6" in sent
    assert call.system


def test_every_tool_is_strict_and_closed(perception: FakePerception, saver: InMemorySaver) -> None:
    model = ScriptedModel([ask_left(), present()])
    copilot = copilot_for(model, perception, saver)

    copilot.start("s1", ASSET, VIEW_SET, FRONT)
    copilot.choose_view("s1", SIDE)

    for tool in [tool for call in model.calls for tool in call.tools]:
        schema = tool["input_schema"]
        assert tool["strict"] is True, tool["name"]
        assert schema["additionalProperties"] is False, tool["name"]
        assert set(schema["required"]) == set(schema["properties"]), tool["name"]
        assert tool["description"], tool["name"]


def test_a_reliable_view_asks_for_approval_of_the_next_step(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel([present()])

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, SIDE)

    assert turn.awaiting == ApprovalRequest(
        view=SIDE,
        explanation="The box sits behind the lower part of the flap, inside the region shown.",
        next_step="Open the flap and reach to the box behind its lower edge.",
    )
    assert model.calls[0].tool_names == {"present_result"}
    assert kinds(turn) == ["perception", "decision", "agent"]
    assert [event.node for event in turn.events] == ["localise", "localise", "present"]


def test_the_view_the_operator_chooses_is_localised_and_decided_again(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    copilot = copilot_for(ScriptedModel([ask_left(), present()]), perception, saver)
    copilot.start("s1", ASSET, VIEW_SET, FRONT)

    turn = copilot.choose_view("s1", SIDE)

    assert turn.located == perception.views[SIDE]
    approval_request(turn)
    assert kinds(turn) == ["human", "perception", "decision", "agent"]
    assert turn.events[0].node == "await_view"
    assert turn.events[0].data == {"view": SIDE}
    assert [event.step for event in turn.events] == [4, 5, 6, 7]
    assert perception.localised == [FRONT, SIDE]


@pytest.mark.parametrize(("approved", "outcome"), [(True, "accepted"), (False, "declined")])
def test_the_operator_s_answer_to_the_next_step_ends_the_session(
    perception: FakePerception, saver: InMemorySaver, approved: bool, outcome: str
) -> None:
    copilot = copilot_for(ScriptedModel([present()]), perception, saver)
    copilot.start("s1", ASSET, VIEW_SET, SIDE)

    turn = copilot.approve("s1", approved=approved)

    assert turn.outcome == outcome
    assert turn.awaiting is None
    assert kinds(turn) == ["human"]
    assert turn.events[0].node == "await_approval"
    assert turn.events[0].data == {"approved": approved}


def test_the_trace_of_a_session_holds_every_event_in_order(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    copilot = copilot_for(ScriptedModel([ask_left(), present()]), perception, saver)
    copilot.start("s1", ASSET, VIEW_SET, FRONT)
    copilot.choose_view("s1", SIDE)
    copilot.approve("s1", approved=True)

    trace = copilot.trace("s1")

    assert [event.kind for event in trace] == [
        "perception",
        "decision",
        "agent",
        "human",
        "perception",
        "decision",
        "agent",
        "human",
    ]
    assert [event.step for event in trace] == list(range(1, 9))


def test_a_session_goes_on_in_another_copilot_on_the_same_store(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    """Two HTTP requests, two Copilot objects: the checkpointer carries the session."""
    copilot_for(ScriptedModel([ask_left()]), perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    turn = copilot_for(ScriptedModel([present()]), perception, saver).choose_view("s1", SIDE)

    approval_request(turn)
    assert [event.step for event in turn.events] == [4, 5, 6, 7]


def test_sessions_do_not_mix(perception: FakePerception, saver: InMemorySaver) -> None:
    copilot = copilot_for(ScriptedModel([ask_left(), present()]), perception, saver)

    copilot.start("s1", ASSET, VIEW_SET, FRONT)
    copilot.start("s2", ASSET, VIEW_SET, SIDE)

    assert [event.data.get("view") for event in copilot.trace("s1")][:1] == [FRONT]
    assert [event.data.get("view") for event in copilot.trace("s2")][:1] == [SIDE]


def test_a_localisation_failure_asks_for_its_own_move(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel(
        [
            tool_use(
                "request_view",
                {
                    "action": "MOVE_BACK",
                    "guidance": "Step back to bring more marks in.",
                    "views": [],
                },
            )
        ]
    )

    request = view_request(
        copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, BLIND)
    )

    assert request.action is Action.MOVE_BACK
    assert request.move_reason == "too few landmarks in view to fit a pose"
    assert request.guidance == "Step back to bring more marks in."


def test_suggest_viewpoints_answers_from_the_perception(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel(
        [tool_use("suggest_viewpoints", {"action": "MOVE_LEFT"}, "c1"), ask_left(call_id="c2")]
    )

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    assert (FRONT, Action.MOVE_LEFT) in perception.suggested
    answer = model.calls[1].messages[-1]
    assert answer["role"] == "user"
    result = answer["content"][0]
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "c1"
    assert SIDE in json.dumps(result["content"]) and "B7_close.png" in json.dumps(result["content"])
    assert kinds(turn) == ["perception", "decision", "tool", "agent"]
    assert turn.events[2].data["tool"] == "suggest_viewpoints"


# ---- what the operator may answer --------------------------------------------------


def test_a_view_that_is_not_a_viewpoint_of_the_set_is_refused(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    copilot = copilot_for(ScriptedModel([ask_left()]), perception, saver)

    with pytest.raises(ValueError, match=r"nowhere\.png"):
        copilot.start("s1", ASSET, VIEW_SET, "nowhere.png")
    copilot.start("s2", ASSET, VIEW_SET, FRONT)
    with pytest.raises(ValueError, match=r"nowhere\.png"):
        copilot.choose_view("s2", "nowhere.png")


def test_the_operator_answers_only_what_the_session_waits_for(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    copilot = copilot_for(ScriptedModel([ask_left(), present()]), perception, saver)
    copilot.start("s1", ASSET, VIEW_SET, FRONT)

    with pytest.raises(ValueError, match="not waiting for an approval"):
        copilot.approve("s1", approved=True)
    copilot.choose_view("s1", SIDE)
    with pytest.raises(ValueError, match="not waiting for a view"):
        copilot.choose_view("s1", FRONT)


def test_a_session_is_started_once_and_must_exist(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    copilot = copilot_for(ScriptedModel([ask_left()]), perception, saver)
    copilot.start("s1", ASSET, VIEW_SET, FRONT)

    with pytest.raises(ValueError, match="already exists"):
        copilot.start("s1", ASSET, VIEW_SET, FRONT)
    with pytest.raises(ValueError, match="no session"):
        copilot.choose_view("nope", SIDE)
    with pytest.raises(ValueError, match="no session"):
        copilot.trace("nope")


# ---- guards: the policy decides, the model only speaks ----------------------------


def test_the_model_cannot_ask_for_another_move_than_the_policy_s(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel(
        [
            tool_use(
                "request_view",
                {"action": "MOVE_RIGHT", "guidance": "Move to the right.", "views": [SIDE]},
            )
        ]
    )

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    request = view_request(turn)
    assert request.action is Action.MOVE_LEFT
    assert SIDE_REASON in request.guidance
    assert "Move to the right." not in request.guidance
    assert checks(turn) == ["action"]
    assert kinds(turn) == ["perception", "decision", "guard", "agent"]


def test_numbers_from_the_model_never_reach_the_operator(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    """The proposal's rule: no confidence percentage written by a language model."""
    model = ScriptedModel(
        [
            tool_use(
                "request_view",
                {
                    "action": "MOVE_LEFT",
                    "guidance": "I am 87% sure: move 40 cm to the left.",
                    "views": [SIDE],
                },
            )
        ]
    )

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    request = view_request(turn)
    assert "87" not in request.guidance and "40 cm" not in request.guidance
    assert SIDE_REASON in request.guidance
    assert request.suggested_views == [SIDE]
    assert checks(turn) == ["numbers"]


def test_numbers_in_a_presented_result_are_replaced_too(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel(
        [
            tool_use(
                "present_result",
                {"explanation": "Found with 92% confidence.", "next_step": "Open the flap."},
            )
        ]
    )

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, SIDE)

    request = approval_request(turn)
    assert not re.search(r"[0-9%]", request.explanation)
    assert request.explanation
    assert request.next_step
    assert checks(turn) == ["numbers"]


def test_views_the_operator_cannot_pick_are_dropped(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel([ask_left(views=[SIDE, "B7_close.png", FRONT, "nowhere.png"])])

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    request = view_request(turn)
    assert request.suggested_views == [SIDE, "B7_close.png"]
    assert request.guidance == LEFT_GUIDANCE
    assert checks(turn) == ["views"]
    assert next(e for e in turn.events if e.kind == "guard").data["dropped"] == [
        FRONT,
        "nowhere.png",
    ]


def test_the_model_cannot_present_an_unreliable_result(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel([present(call_id="c1"), ask_left(call_id="c2")])

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    view_request(turn)
    assert len(model.calls) == 2
    refusal = model.calls[1].messages[-1]["content"][0]
    assert refusal["type"] == "tool_result"
    assert refusal["tool_use_id"] == "c1"
    assert refusal["is_error"] is True
    assert checks(turn) == ["tool"]


def test_the_model_cannot_ask_for_a_view_when_the_result_is_reliable(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    model = ScriptedModel([ask_left(call_id="c1"), present(call_id="c2")])

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, SIDE)

    approval_request(turn)
    assert checks(turn) == ["tool"]


# ---- fallbacks: the loop never stops for the model --------------------------------


@pytest.mark.parametrize(
    ("step", "reason"),
    [(UNAVAILABLE, "unavailable"), (ModelTurn(content=[], stop_reason="refusal"), "refusal")],
)
def test_without_the_model_the_operator_gets_the_policy_s_own_words(
    perception: FakePerception, saver: InMemorySaver, step: Step, reason: str
) -> None:
    model = ScriptedModel([step])

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    request = view_request(turn)
    assert request.action is Action.MOVE_LEFT
    assert SIDE_REASON in request.guidance
    assert request.suggested_views == [SIDE, "B7_close.png"]
    assert kinds(turn) == ["perception", "decision", "fallback", "agent"]
    assert turn.events[2].data == {"reason": reason}
    assert len(model.calls) == 1


def test_without_the_model_a_reliable_result_is_still_presented(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    turn = copilot_for(ScriptedModel([UNAVAILABLE]), perception, saver).start(
        "s1", ASSET, VIEW_SET, SIDE
    )

    request = approval_request(turn)
    assert request.explanation and request.next_step
    assert kinds(turn) == ["perception", "decision", "fallback", "agent"]


def test_a_model_that_never_finishes_is_cut_off(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    endless = [
        tool_use("suggest_viewpoints", {"action": "MOVE_LEFT"}, f"c{index}")
        for index in range(MAX_MODEL_CALLS + 2)
    ]
    model = ScriptedModel(list(endless))

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    assert len(model.calls) == MAX_MODEL_CALLS
    assert SIDE_REASON in view_request(turn).guidance
    assert [e.data for e in turn.events if e.kind == "fallback"] == [{"reason": "budget"}]


def test_a_model_that_only_talks_is_asked_once_more_for_its_tool(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    talk = {"type": "text", "text": "You should move left."}
    model = ScriptedModel([ModelTurn(content=[talk], stop_reason="end_turn"), ask_left()])

    turn = copilot_for(model, perception, saver).start("s1", ASSET, VIEW_SET, FRONT)

    assert view_request(turn).guidance == LEFT_GUIDANCE
    assert len(model.calls) == 2
    assert model.calls[1].messages[-2] == {"role": "assistant", "content": [talk]}
    assert model.calls[1].messages[-1]["role"] == "user"


# ---- the history the model sees ----------------------------------------------------


def test_the_model_history_is_only_ever_appended(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    """Thinking blocks stay valid only in the conversation that produced them."""
    turns = [
        tool_use("suggest_viewpoints", {"action": "MOVE_LEFT"}, "c1"),
        ask_left(call_id="c2"),
        present(call_id="c3"),
    ]
    model = ScriptedModel(list(turns))
    copilot = copilot_for(model, perception, saver)

    copilot.start("s1", ASSET, VIEW_SET, FRONT)
    copilot.choose_view("s1", SIDE)

    assert len(model.calls) == 3
    for index, (before, after) in enumerate(zip(model.calls, model.calls[1:], strict=False)):
        assert after.messages[: len(before.messages)] == before.messages
        assert after.messages[len(before.messages)] == {
            "role": "assistant",
            "content": turns[index].content,
        }


def test_a_request_to_the_operator_is_answered_before_the_next_view(
    perception: FakePerception, saver: InMemorySaver
) -> None:
    """Every tool call needs its result before the API takes the next message."""
    model = ScriptedModel([ask_left(call_id="c1"), present(call_id="c2")])
    copilot = copilot_for(model, perception, saver)
    copilot.start("s1", ASSET, VIEW_SET, FRONT)

    copilot.choose_view("s1", SIDE)

    first, second = model.calls
    following = second.messages[len(first.messages) + 1]
    assert following["role"] == "user"
    assert following["content"][0]["type"] == "tool_result"
    assert following["content"][0]["tool_use_id"] == "c1"
    assert SIDE in json.dumps(following, ensure_ascii=False)


# ---- the graph -----------------------------------------------------------------------


def test_the_graph_has_the_loop_s_nodes(perception: FakePerception, saver: InMemorySaver) -> None:
    graph = copilot_for(ScriptedModel(), perception, saver).graph

    nodes = set(graph.get_graph().nodes)

    assert {"localise", "guide", "await_view", "present", "await_approval"} <= nodes
    assert "await_view" in graph.get_graph().draw_mermaid()
