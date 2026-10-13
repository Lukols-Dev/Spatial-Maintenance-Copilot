"""The agent's loop as a LangGraph graph: localise, decide, speak, wait for the operator.

    START -> localise -> (reliable?) -> present -> await_approval -> END
                     \\-> (not reliable) -> guide -> await_view -> localise

localise asks the perception for the viewpoint and the policy's decision; the
branch is that decision, a measured fact, never the model's. guide and present
are the model's turns: it explains the decision and acts through the tools of
its branch, and guards hold its output to the policy. await_view and
await_approval stop the graph until the operator answers; the checkpointer
keeps the session in between, so each answer can come in another request.

Every node appends TraceEvents, numbered through the session: the trace is
the perception-to-action record the operator and the judges read.
"""

import json
import logging
import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from smc_core.contracts import Action

from smc_agent.contracts import (
    ApprovalRequest,
    EventKind,
    Located,
    TraceEvent,
    Turn,
    ViewRequest,
)
from smc_agent.model import ChatModel, ModelUnavailable, ToolCall
from smc_agent.perception import Perception
from smc_agent.tools import GUIDE_TOOLS, PRESENT_TOOLS
from smc_agent.wording import (
    EXPLANATION,
    NEXT_STEP,
    SYSTEM,
    guidance_for,
    has_numbers,
    observation,
)

# Model calls one turn may take before the policy's own words are used.
MAX_MODEL_CALLS = 4

# Why the model gave no answer goes to the log, not the trace: an AWS error can
# name the account, and the trace is shown to every visitor.
logger = logging.getLogger(__name__)


class SessionError(ValueError):
    """A call the session cannot take; the subclass says why."""


class NoSession(SessionError):
    pass


class SessionExists(SessionError):
    pass


class NotWaiting(SessionError):
    """The operator answered something the session is not asking."""


class NotAViewpoint(SessionError):
    pass


Message = dict[str, Any]
Event = tuple[EventKind, str, dict[str, Any]]


class SessionState(TypedDict, total=False):
    """The graph's state, all of it JSON, as the checkpointer stores it."""

    asset_id: str
    view_set: str
    view: str
    located: dict[str, Any]  # Located
    messages: list[Message]  # the model's history, only ever appended
    owed: list[Message]  # tool results the next user message must open with
    trace: Annotated[list[dict[str, Any]], operator.add]  # TraceEvent
    awaiting: dict[str, Any] | None  # ViewRequest or ApprovalRequest
    outcome: Literal["accepted", "declined"] | None


@dataclass
class _Conversation:
    """One node's exchange with the model, until it calls the tool that ends the turn."""

    messages: list[Message]
    events: list[Event] = field(default_factory=list)
    finished: ToolCall | None = None
    owed: list[Message] = field(default_factory=list)
    fallback: str | None = None


def _result(call_id: str, content: str, is_error: bool = False) -> Message:
    block: Message = {"type": "tool_result", "tool_use_id": call_id, "content": content}
    if is_error:
        block["is_error"] = True
    return block


class Copilot:
    """Sessions of the agent: start one at a viewpoint, then answer what it asks.

    perception_for gives the perception of an asset's atlas and a view set;
    the checkpointer keeps sessions between calls, InMemorySaver locally and
    DynamoDB on AWS.
    """

    def __init__(
        self,
        model: ChatModel,
        perception_for: Callable[[str, str], Perception],
        checkpointer: BaseCheckpointSaver[Any],
    ) -> None:
        self.model = model
        self.perception_for = perception_for
        graph = StateGraph(SessionState)
        graph.add_node("localise", self._localise)
        graph.add_node("guide", self._guide)
        graph.add_node("present", self._present)
        graph.add_node("await_view", self._await_view)
        graph.add_node("await_approval", self._await_approval)
        graph.add_edge(START, "localise")
        graph.add_conditional_edges("localise", self._branch, ["guide", "present"])
        graph.add_edge("guide", "await_view")
        graph.add_edge("await_view", "localise")
        graph.add_edge("present", "await_approval")
        graph.add_edge("await_approval", END)
        self.graph: CompiledStateGraph[SessionState, None, SessionState, SessionState] = (
            graph.compile(checkpointer=checkpointer)
        )

    # ---- the API ---------------------------------------------------------------

    def start(self, session_id: str, asset_id: str, view_set: str, view: str) -> Turn:
        """A new session at view; the first turn runs until the operator is asked."""
        if self._state(session_id):
            raise SessionExists(f"session {session_id!r} already exists")
        self._check_view(self.perception_for(asset_id, view_set), view, view_set)
        initial: SessionState = {
            "asset_id": asset_id,
            "view_set": view_set,
            "view": view,
            "messages": [],
            "owed": [],
            "trace": [],
            "awaiting": None,
            "outcome": None,
        }
        self.graph.invoke(initial, self._config(session_id))
        return self._turn(session_id, 0)

    def choose_view(self, session_id: str, view: str) -> Turn:
        """The operator's next viewpoint, after a ViewRequest."""
        state = self._waiting(session_id, "view")
        self._check_view(self._perception(state), view, state["view_set"])
        before = len(state["trace"])
        self.graph.invoke(Command(resume={"view": view}), self._config(session_id))
        return self._turn(session_id, before)

    def approve(self, session_id: str, approved: bool) -> Turn:
        """The operator's answer to an ApprovalRequest; it ends the session."""
        state = self._waiting(session_id, "approval")
        before = len(state["trace"])
        self.graph.invoke(Command(resume={"approved": approved}), self._config(session_id))
        return self._turn(session_id, before)

    def trace(self, session_id: str) -> list[TraceEvent]:
        """Every event of the session, in order."""
        return [TraceEvent.model_validate(event) for event in self._existing(session_id)["trace"]]

    def turn(self, session_id: str) -> Turn:
        """Where the session stands, with every event so far."""
        return self._turn(session_id, 0)

    # ---- the nodes -------------------------------------------------------------

    def _localise(self, state: SessionState) -> SessionState:
        located = self._perception(state).localise(state["view"])
        decision = located.decision
        message: Message = {
            "role": "user",
            "content": [*state["owed"], {"type": "text", "text": observation(located)}],
        }
        failure = located.localisation.failure
        return {
            "located": located.model_dump(mode="json"),
            "messages": [*state["messages"], message],
            "owed": [],
            "trace": _events(
                state,
                "localise",
                [
                    (
                        "perception",
                        f"localised {located.view}"
                        + ("" if failure is None else f": {failure.value}"),
                        {"view": located.view},
                    ),
                    (
                        "decision",
                        "reliable" if decision.reliable else f"not reliable: {decision.action}",
                        {
                            "reliable": decision.reliable,
                            "action": decision.action.value,
                            "move_reason": decision.move_reason,
                            "reasons": decision.reasons,
                        },
                    ),
                ],
            ),
        }

    @staticmethod
    def _branch(state: SessionState) -> str:
        return "present" if Located.model_validate(state["located"]).decision.reliable else "guide"

    def _guide(self, state: SessionState) -> SessionState:
        located = Located.model_validate(state["located"])
        decision = located.decision
        perception = self._perception(state)
        talk = self._converse(state, perception, "request_view", GUIDE_TOOLS)

        if talk.finished is None:
            assert talk.fallback is not None
            talk.events.append(
                (
                    "fallback",
                    f"the model gave no answer: {talk.fallback}",
                    {"reason": talk.fallback},
                )
            )
            guidance = guidance_for(located)
            views = perception.suggest(located.view, decision.action)
        else:
            asked = talk.finished.input
            guidance = str(asked.get("guidance", "")).strip()
            reword = not guidance
            if asked.get("action") != decision.action.value:
                talk.events.append(
                    (
                        "guard",
                        f"the model asked for {asked.get('action')}; the policy decided {decision.action}",
                        {"check": "action", "asked": asked.get("action")},
                    )
                )
                reword = True
            if has_numbers(guidance):
                talk.events.append(("guard", "the model wrote numbers", {"check": "numbers"}))
                reword = True
            if reword:
                guidance = guidance_for(located)
            allowed = set(perception.viewpoints()) - {located.view}
            named = [str(view) for view in asked.get("views", [])]
            views = [view for view in named if view in allowed]
            dropped = [view for view in named if view not in allowed]
            if dropped:
                talk.events.append(
                    (
                        "guard",
                        "views the operator cannot choose",
                        {"check": "views", "dropped": dropped},
                    )
                )

        request = ViewRequest(
            view=located.view,
            action=decision.action,
            move_reason=decision.move_reason,
            guidance=guidance,
            suggested_views=views,
        )
        talk.events.append(
            (
                "agent",
                f"asked for {decision.action}",
                {"action": decision.action.value, "views": views},
            )
        )
        return {
            "messages": talk.messages,
            "owed": talk.owed,
            "awaiting": request.model_dump(mode="json"),
            "trace": _events(state, "guide", talk.events),
        }

    def _present(self, state: SessionState) -> SessionState:
        located = Located.model_validate(state["located"])
        talk = self._converse(state, self._perception(state), "present_result", PRESENT_TOOLS)

        if talk.finished is None:
            assert talk.fallback is not None
            talk.events.append(
                (
                    "fallback",
                    f"the model gave no answer: {talk.fallback}",
                    {"reason": talk.fallback},
                )
            )
            explanation, next_step = EXPLANATION, NEXT_STEP
        else:
            explanation = str(talk.finished.input.get("explanation", "")).strip() or EXPLANATION
            next_step = str(talk.finished.input.get("next_step", "")).strip() or NEXT_STEP
            if has_numbers(explanation) or has_numbers(next_step):
                talk.events.append(("guard", "the model wrote numbers", {"check": "numbers"}))
                explanation = EXPLANATION if has_numbers(explanation) else explanation
                next_step = NEXT_STEP if has_numbers(next_step) else next_step

        request = ApprovalRequest(view=located.view, explanation=explanation, next_step=next_step)
        talk.events.append(("agent", "presented the result for approval", {"next_step": next_step}))
        return {
            "messages": talk.messages,
            "owed": talk.owed,
            "awaiting": request.model_dump(mode="json"),
            "trace": _events(state, "present", talk.events),
        }

    def _await_view(self, state: SessionState) -> SessionState:
        answer = interrupt(state["awaiting"])
        view = str(answer["view"])
        return {
            "view": view,
            "awaiting": None,
            "trace": _events(
                state, "await_view", [("human", f"the operator chose {view}", {"view": view})]
            ),
        }

    def _await_approval(self, state: SessionState) -> SessionState:
        answer = interrupt(state["awaiting"])
        approved = bool(answer["approved"])
        return {
            "awaiting": None,
            "outcome": "accepted" if approved else "declined",
            "trace": _events(
                state,
                "await_approval",
                [
                    (
                        "human",
                        "the operator approved" if approved else "the operator declined",
                        {"approved": approved},
                    )
                ],
            ),
        }

    # ---- the model's turn ----------------------------------------------------------

    def _converse(
        self, state: SessionState, perception: Perception, finish: str, tools: list[dict[str, Any]]
    ) -> _Conversation:
        """Call the model until it calls `finish`, within MAX_MODEL_CALLS.

        Every answer is appended to the history as it came. A tool of the
        branch gets its result at once; a tool from outside it gets an error
        result and a guard event. The result of `finish` is owed: it opens the
        user message that brings the operator's next viewpoint.
        """
        talk = _Conversation(messages=list(state["messages"]))
        offered = {tool["name"] for tool in tools}
        for _ in range(MAX_MODEL_CALLS):
            try:
                turn = self.model.respond(SYSTEM, talk.messages, tools)
            except ModelUnavailable as error:
                logger.warning("the model gave no answer: %s", error)
                talk.fallback = "unavailable"
                return talk
            if turn.stop_reason == "refusal" or not turn.content:
                logger.warning("the model declined: stop_reason %s", turn.stop_reason)
                talk.fallback = "refusal"
                return talk
            talk.messages.append({"role": "assistant", "content": turn.content})

            calls = turn.tool_calls
            if not calls:
                nudge = f"End your turn by calling {finish}."
                talk.messages.append({"role": "user", "content": [{"type": "text", "text": nudge}]})
                continue

            results: list[Message] = []
            for call in calls:
                if call.name == finish and talk.finished is None:
                    talk.finished = call
                elif call.name == "suggest_viewpoints" and call.name in offered:
                    views = perception.suggest(state["view"], Action(call.input["action"]))
                    results.append(_result(call.id, json.dumps(views)))
                    talk.events.append(
                        (
                            "tool",
                            f"suggest_viewpoints {call.input['action']}",
                            {"tool": call.name, "views": views},
                        )
                    )
                else:
                    results.append(
                        _result(call.id, f"{call.name} is not available now", is_error=True)
                    )
                    talk.events.append(
                        (
                            "guard",
                            f"{call.name} is not a tool of this turn",
                            {"check": "tool", "tool": call.name},
                        )
                    )
            if talk.finished is not None:
                talk.owed = [*results, _result(talk.finished.id, "sent to the operator")]
                return talk
            talk.messages.append({"role": "user", "content": results})

        talk.fallback = "budget"
        return talk

    # ---- helpers -----------------------------------------------------------------

    @staticmethod
    def _config(session_id: str) -> Any:
        return {"configurable": {"thread_id": session_id}}

    def _perception(self, state: SessionState) -> Perception:
        return self.perception_for(state["asset_id"], state["view_set"])

    @staticmethod
    def _check_view(perception: Perception, view: str, view_set: str) -> None:
        if view not in perception.viewpoints():
            raise NotAViewpoint(f"{view} is not a viewpoint of view set {view_set!r}")

    def _state(self, session_id: str) -> SessionState:
        return cast(SessionState, self.graph.get_state(self._config(session_id)).values)

    def _existing(self, session_id: str) -> SessionState:
        state = self._state(session_id)
        if not state:
            raise NoSession(f"no session {session_id!r}")
        return state

    def _waiting(self, session_id: str, kind: str) -> SessionState:
        state = self._existing(session_id)
        awaiting = state.get("awaiting")
        if awaiting is None or awaiting["kind"] != kind:
            what = "an approval" if kind == "approval" else "a view"
            raise NotWaiting(f"session {session_id!r} is not waiting for {what}")
        return state

    def _turn(self, session_id: str, before: int) -> Turn:
        state = self._existing(session_id)
        located = state.get("located")
        return Turn.model_validate(
            {
                "session_id": session_id,
                "asset_id": state["asset_id"],
                "view_set": state["view_set"],
                "located": located,
                "awaiting": state.get("awaiting"),
                "outcome": state.get("outcome"),
                "events": state["trace"][before:],
            }
        )


def _events(state: SessionState, node: str, events: list[Event]) -> list[dict[str, Any]]:
    """The events as the trace stores them, numbered on from the session's last."""
    first = len(state.get("trace", [])) + 1
    return [
        TraceEvent(step=first + index, kind=kind, node=node, summary=summary, data=data).model_dump(
            mode="json"
        )
        for index, (kind, summary, data) in enumerate(events)
    ]
