"""The model adapter: what goes to Claude on Bedrock and what comes back.

A fake client stands for anthropic.AnthropicBedrockMantle: it records the
keyword arguments of messages.create and answers with blocks that have the
SDK's to_dict(). Nothing here reaches AWS.
"""

import copy
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx2
import pytest
from smc_agent.bedrock import DEFAULT_MODEL_ID, BedrockChatModel
from smc_agent.model import ModelTurn, ModelUnavailable, ToolCall

TOOLS: list[dict[str, Any]] = [
    {
        "name": "request_view",
        "description": "Ask the operator for another viewpoint.",
        "input_schema": {
            "type": "object",
            "properties": {"guidance": {"type": "string"}},
            "required": ["guidance"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]
MESSAGES: list[dict[str, Any]] = [{"role": "user", "content": "B1_close.png: MOVE_LEFT"}]


@dataclass
class Block:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)


@dataclass
class Response:
    content: list[Block]
    stop_reason: str


@dataclass
class FakeMessages:
    answer: Response | Exception
    sent: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Response:
        self.sent.append(kwargs)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class FakeClient:
    def __init__(self, answer: Response | Exception) -> None:
        self.messages = FakeMessages(answer)


def answered(*blocks: dict[str, Any], stop_reason: str = "end_turn") -> FakeClient:
    return FakeClient(Response([Block(block) for block in blocks], stop_reason))


def test_the_default_model_is_claude_opus_on_bedrock() -> None:
    assert DEFAULT_MODEL_ID == "anthropic.claude-opus-5-5"


def test_a_request_carries_the_model_the_tools_and_the_effort() -> None:
    client = answered({"type": "text", "text": "ok"})

    BedrockChatModel(client, effort="low").respond("You guide an operator.", MESSAGES, TOOLS)

    sent = client.messages.sent[0]
    assert sent["model"] == DEFAULT_MODEL_ID
    assert sent["system"] == "You guide an operator."
    assert sent["messages"] == MESSAGES
    assert sent["tools"] == TOOLS
    assert sent["tool_choice"] == {"type": "auto"}
    assert sent["output_config"] == {"effort": "low"}
    assert sent["max_tokens"] > 0
    # Claude Opus 5.5 rejects disabling thinking or giving it a budget; effort is the control.
    assert "thinking" not in sent


def test_another_model_and_effort_can_be_chosen() -> None:
    client = answered({"type": "text", "text": "ok"})

    BedrockChatModel(client, model_id="anthropic.claude-sonnet-5-5", effort="medium").respond(
        "s", MESSAGES, TOOLS
    )

    assert client.messages.sent[0]["model"] == "anthropic.claude-sonnet-5-5"
    assert client.messages.sent[0]["output_config"] == {"effort": "medium"}


def test_the_answer_comes_back_as_blocks_to_append_unchanged() -> None:
    blocks = [
        {"type": "thinking", "thinking": "", "signature": "c2lnbmF0dXJl"},
        {"type": "text", "text": "Asking for the left side."},
        {"type": "tool_use", "id": "t1", "name": "request_view", "input": {"guidance": "Go left."}},
    ]

    turn = BedrockChatModel(answered(*blocks, stop_reason="tool_use")).respond("s", MESSAGES, TOOLS)

    assert turn == ModelTurn(content=blocks, stop_reason="tool_use")


def test_the_call_leaves_the_history_it_was_given_alone() -> None:
    messages = copy.deepcopy(MESSAGES)

    BedrockChatModel(answered({"type": "text", "text": "ok"})).respond("s", messages, TOOLS)

    assert messages == MESSAGES


def test_an_api_error_is_a_model_that_is_unavailable() -> None:
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://bedrock.test"))

    with pytest.raises(ModelUnavailable):
        BedrockChatModel(FakeClient(error)).respond("s", MESSAGES, TOOLS)


def test_tool_calls_are_read_from_the_tool_use_blocks() -> None:
    turn = ModelTurn(
        content=[
            {"type": "text", "text": "Two things."},
            {"type": "tool_use", "id": "t1", "name": "suggest_viewpoints", "input": {"a": 1}},
            {"type": "tool_use", "id": "t2", "name": "request_view", "input": {}},
        ],
        stop_reason="tool_use",
    )

    assert turn.tool_calls == [
        ToolCall(id="t1", name="suggest_viewpoints", input={"a": 1}),
        ToolCall(id="t2", name="request_view", input={}),
    ]


def test_a_turn_without_tool_use_has_no_tool_calls() -> None:
    assert (
        ModelTurn(content=[{"type": "text", "text": "hi"}], stop_reason="end_turn").tool_calls == []
    )
