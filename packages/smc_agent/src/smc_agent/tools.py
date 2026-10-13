"""The tools the model is offered, as the Messages API takes them.

Each is strict and closed: every property required, nothing else allowed, so a
call either matches the schema or does not come. Which tools a node offers is
the guard against the model acting outside its branch: when the result is
reliable there is no request_view, and when it is not there is no
present_result.
"""

from typing import Any

from smc_core.contracts import Action

MOVES = [action.value for action in Action if action is not Action.ACCEPT]


def _tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
        "strict": True,
    }


SUGGEST_VIEWPOINTS = _tool(
    "suggest_viewpoints",
    "List the recorded viewpoints that lie in the direction of a move from the current one, "
    "best first. Use it to point the operator at viewpoints they can choose.",
    {"action": {"type": "string", "enum": MOVES, "description": "the move"}},
)

REQUEST_VIEW = _tool(
    "request_view",
    "Ask the operator for another viewpoint. Call it once, to end your turn, when the "
    "localisation is not reliable. action must be the policy's move.",
    {
        "action": {"type": "string", "enum": MOVES, "description": "the policy's move"},
        "guidance": {
            "type": "string",
            "description": "one or two short sentences to the operator, without numbers",
        },
        "views": {
            "type": "array",
            "items": {"type": "string"},
            "description": "recorded viewpoints to suggest, from suggest_viewpoints",
        },
    },
)

PRESENT_RESULT = _tool(
    "present_result",
    "Present a reliable localisation and propose the next maintenance step for the operator "
    "to approve. Call it once, to end your turn.",
    {
        "explanation": {
            "type": "string",
            "description": "where the hidden component is, in the operator's view, without numbers",
        },
        "next_step": {
            "type": "string",
            "description": "the next maintenance step, without numbers",
        },
    },
)

GUIDE_TOOLS = [SUGGEST_VIEWPOINTS, REQUEST_VIEW]
PRESENT_TOOLS = [PRESENT_RESULT]
