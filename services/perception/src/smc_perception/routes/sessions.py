"""Sessions of the agent: start one at a viewpoint, then answer what it asks.

Every answer is a SessionTurn: the agent's turn (what it asks, the events the
call added) and the localisation of the current viewpoint, to draw.
"""

import uuid
from collections.abc import Callable

from fastapi import APIRouter
from smc_agent.contracts import Turn
from smc_agent.copilot import Copilot, NoSession, NotAViewpoint, NotWaiting, SessionExists

from smc_perception.agent import CHECKPOINTER, WorkspacePerception, agent_model, model_name
from smc_perception.errors import Conflict, Invalid, NotFound
from smc_perception.models import ApprovalAnswer, SessionStart, SessionTurn, ViewChoice
from smc_perception.routes import WorkspaceDep
from smc_perception.workspace import WorkspaceFiles

router = APIRouter(tags=["sessions"])


class _Agent:
    """A Copilot for one request, and the perceptions it opened, kept for the answer."""

    def __init__(self, workspace: WorkspaceFiles) -> None:
        self.workspace = workspace
        self.opened: dict[tuple[str, str], WorkspacePerception] = {}
        self.copilot = Copilot(agent_model(), self.perception, CHECKPOINTER)

    def perception(self, asset_id: str, view_set: str) -> WorkspacePerception:
        key = (asset_id, view_set)
        if key not in self.opened:
            self.opened[key] = WorkspacePerception(self.workspace, asset_id, view_set)
        return self.opened[key]

    def run(self, call: Callable[[Copilot], Turn]) -> SessionTurn:
        try:
            turn = call(self.copilot)
        except NoSession as error:
            raise NotFound(str(error)) from error
        except (SessionExists, NotWaiting) as error:
            raise Conflict(str(error)) from error
        except NotAViewpoint as error:
            raise Invalid(str(error)) from error
        result = None
        if turn.located is not None:
            result = self.perception(turn.asset_id, turn.view_set).result(turn.located.view)
        return SessionTurn(turn=turn, result=result, model=model_name())


@router.post("/sessions", status_code=201)
def start_session(body: SessionStart, workspace: WorkspaceDep) -> SessionTurn:
    """A new session; the agent localises the viewpoint and asks its first question."""
    session_id = uuid.uuid4().hex
    return _Agent(workspace).run(
        lambda copilot: copilot.start(session_id, body.asset_id, body.view_set, body.view)
    )


@router.get("/sessions/{session_id}")
def get_session(session_id: str, workspace: WorkspaceDep) -> SessionTurn:
    """Where the session stands, with every event of its trace."""
    return _Agent(workspace).run(lambda copilot: copilot.turn(session_id))


@router.post("/sessions/{session_id}/view")
def choose_view(session_id: str, body: ViewChoice, workspace: WorkspaceDep) -> SessionTurn:
    """The operator's next viewpoint, after the agent asked for one."""
    return _Agent(workspace).run(lambda copilot: copilot.choose_view(session_id, body.view))


@router.post("/sessions/{session_id}/approval")
def answer_approval(session_id: str, body: ApprovalAnswer, workspace: WorkspaceDep) -> SessionTurn:
    """The operator's answer to the next step the agent proposed; it ends the session."""
    return _Agent(workspace).run(lambda copilot: copilot.approve(session_id, body.approved))
