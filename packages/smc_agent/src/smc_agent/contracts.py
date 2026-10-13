"""What the agent works from and what it hands back.

The perception reports a viewpoint as a Located: the geometry and the policy's
verdict on it. The agent answers with a Turn: what the operator is asked next,
a ViewRequest or an ApprovalRequest, and the TraceEvents the turn added. The
numbers in a request come from the policy; only guidance, explanation and
next_step are words of the model, and those carry no numbers.
"""

from typing import Annotated, Any, Literal

from pydantic import Field
from smc_core.contracts import Action, Contract, Decision, Localisation


class Located(Contract):
    """One viewpoint as the perception reports it: the geometry and the policy's verdict."""

    view: str
    localisation: Localisation
    decision: Decision


class ViewRequest(Contract):
    """The result is not reliable: the operator is asked for another viewpoint."""

    kind: Literal["view"] = "view"
    view: str = Field(description="the viewpoint just localised")
    action: Action = Field(description="the policy's move")
    move_reason: str = Field(description="the policy's fact the move follows from")
    guidance: str = Field(description="the agent's words to the operator, without numbers")
    suggested_views: list[str] = Field(description="recorded viewpoints that fit the move")


class ApprovalRequest(Contract):
    """The result is reliable: the operator approves the next maintenance step, or not."""

    kind: Literal["approval"] = "approval"
    view: str
    explanation: str = Field(description="the agent's words on the result, without numbers")
    next_step: str = Field(description="the step the operator is asked to approve")


EventKind = Literal["perception", "decision", "agent", "tool", "human", "guard", "fallback"]


class TraceEvent(Contract):
    """One step of a session, as the trace shows it.

    perception and decision come from the geometry and the policy, agent and
    tool from the model, human from the operator. A guard is the agent's
    output corrected to the policy; a fallback is the policy's own words used
    when the model gave none.
    """

    step: int = Field(description="1 for the first event of the session, then one more each")
    kind: EventKind
    node: str = Field(description="the graph node that wrote it")
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


Request = Annotated[ViewRequest | ApprovalRequest, Field(discriminator="kind")]


class Turn(Contract):
    """Where a session stands after a call: the viewpoint, what is asked, what happened."""

    session_id: str
    asset_id: str
    view_set: str
    located: Located | None
    awaiting: Request | None = Field(description="None once the session has ended")
    outcome: Literal["accepted", "declined"] | None
    events: list[TraceEvent] = Field(description="the events this call added")
