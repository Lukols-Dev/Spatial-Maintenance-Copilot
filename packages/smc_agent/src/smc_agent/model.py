"""The language model as the agent sees it: one call, blocks in and blocks out.

The blocks are the Messages API's, as plain dictionaries: the agent appends
every answer to its history unchanged, thinking blocks included, since they
stay valid only in the conversation that produced them.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    """One answer of the model: its content blocks and why it stopped."""

    content: list[dict[str, Any]]
    stop_reason: str

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [
            ToolCall(id=block["id"], name=block["name"], input=block["input"])
            for block in self.content
            if block.get("type") == "tool_use"
        ]


class ModelUnavailable(Exception):
    """The model gave no answer: not configured, unreachable, or an API error."""


class ChatModel(Protocol):
    def respond(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn: ...


class NoModel:
    """The model when none is configured: every call is unavailable.

    The agent then speaks with the policy's own words, so a session still runs
    without AWS credentials, and its trace says so.
    """

    def __init__(self, why: str) -> None:
        self.why = why

    def respond(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        raise ModelUnavailable(self.why)
