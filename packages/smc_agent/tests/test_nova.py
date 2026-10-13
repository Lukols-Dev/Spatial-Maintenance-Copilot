"""The Nova adapter: what goes to Converse and what comes back as the Messages API's blocks.

A fake client stands for boto3's bedrock-runtime: it records the keyword
arguments of converse and answers as Converse does. Nothing here reaches AWS.
"""

import copy
from dataclasses import dataclass, field
from typing import Any

import pytest
from botocore.exceptions import ClientError
from smc_agent.model import ModelTurn, ModelUnavailable
from smc_agent.nova import DEFAULT_MODEL_ID, NovaChatModel

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"guidance": {"type": "string"}},
    "required": ["guidance"],
    "additionalProperties": False,
}
TOOLS: list[dict[str, Any]] = [
    {
        "name": "request_view",
        "description": "Ask the operator for another viewpoint.",
        "input_schema": SCHEMA,
        "strict": True,
    }
]
MESSAGES: list[dict[str, Any]] = [{"role": "user", "content": "B1_close.png: MOVE_LEFT"}]


@dataclass
class FakeClient:
    answer: dict[str, Any] | Exception
    sent: list[dict[str, Any]] = field(default_factory=list)

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.sent.append(copy.deepcopy(kwargs))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def answered(*content: dict[str, Any], stop_reason: str = "end_turn") -> FakeClient:
    return FakeClient(
        {
            "output": {"message": {"role": "assistant", "content": list(content)}},
            "stopReason": stop_reason,
            "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        }
    )


def sent_by(effort: str = "low", messages: list[dict[str, Any]] = MESSAGES) -> dict[str, Any]:
    client = answered({"text": "ok"})
    NovaChatModel(client, effort=effort).respond("You guide an operator.", messages, TOOLS)
    return client.sent[0]


def test_the_default_model_is_nova_2_lite_through_the_eu_profile() -> None:
    assert DEFAULT_MODEL_ID == "eu.amazon.nova-2-lite-v1:0"


def test_a_request_carries_the_model_the_tools_and_the_effort() -> None:
    sent = sent_by("low")

    assert sent["modelId"] == DEFAULT_MODEL_ID
    assert sent["system"] == [{"text": "You guide an operator."}]
    assert sent["messages"] == [{"role": "user", "content": [{"text": "B1_close.png: MOVE_LEFT"}]}]
    assert sent["toolConfig"] == {
        "tools": [
            {
                "toolSpec": {
                    "name": "request_view",
                    "description": "Ask the operator for another viewpoint.",
                    "inputSchema": {"json": SCHEMA},
                }
            }
        ],
        "toolChoice": {"auto": {}},
    }
    assert sent["additionalModelRequestFields"] == {
        "reasoningConfig": {"type": "enabled", "maxReasoningEffort": "low"}
    }
    # Below these Nova fails with "maxTokens is insufficient" once it reasons.
    assert sent["inferenceConfig"] == {"maxTokens": 15000, "temperature": 0}


def test_medium_effort_has_room_for_its_reasoning() -> None:
    sent = sent_by("medium")

    assert sent["additionalModelRequestFields"]["reasoningConfig"]["maxReasoningEffort"] == "medium"
    assert sent["inferenceConfig"]["maxTokens"] == 30000


@pytest.mark.parametrize("effort", ["high", "xhigh", "max"])
def test_from_high_up_nova_reasons_at_high_with_no_inference_config(effort: str) -> None:
    """At high Nova refuses a token limit or a temperature; it has no level above."""
    sent = sent_by(effort)

    assert sent["additionalModelRequestFields"]["reasoningConfig"]["maxReasoningEffort"] == "high"
    assert "inferenceConfig" not in sent


def test_the_history_goes_in_converse_s_blocks() -> None:
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "B1_close.png: MOVE_LEFT"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "c2lnbmF0dXJl"},
                {"type": "text", "text": "Looking."},
                {"type": "tool_use", "id": "t1", "name": "suggest_viewpoints", "input": {"a": 1}},
                {"type": "tool_use", "id": "t2", "name": "present_result", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": '["B5_close.png"]'},
                {
                    "type": "tool_result",
                    "tool_use_id": "t2",
                    "content": "present_result is not available now",
                    "is_error": True,
                },
            ],
        },
    ]

    assert sent_by(messages=messages)["messages"] == [
        {"role": "user", "content": [{"text": "B1_close.png: MOVE_LEFT"}]},
        {
            "role": "assistant",
            "content": [
                {"text": "Looking."},
                {"toolUse": {"toolUseId": "t1", "name": "suggest_viewpoints", "input": {"a": 1}}},
                {"toolUse": {"toolUseId": "t2", "name": "present_result", "input": {}}},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "t1",
                        "content": [{"text": '["B5_close.png"]'}],
                        "status": "success",
                    }
                },
                {
                    "toolResult": {
                        "toolUseId": "t2",
                        "content": [{"text": "present_result is not available now"}],
                        "status": "error",
                    }
                },
            ],
        },
    ]


def test_user_messages_in_a_row_go_as_one() -> None:
    """A turn the model did not answer, then the next view: Converse wants the roles to alternate."""
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "B1_close.png: MOVE_LEFT"}]},
        {"role": "user", "content": [{"type": "text", "text": "B5_close.png: ACCEPT"}]},
    ]

    assert sent_by(messages=messages)["messages"] == [
        {
            "role": "user",
            "content": [{"text": "B1_close.png: MOVE_LEFT"}, {"text": "B5_close.png: ACCEPT"}],
        }
    ]


def test_blank_text_is_left_out() -> None:
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "B1_close.png: MOVE_LEFT"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "  "}]},
    ]

    assert sent_by(messages=messages)["messages"] == [
        {"role": "user", "content": [{"text": "B1_close.png: MOVE_LEFT"}]}
    ]


def test_the_answer_comes_back_as_text_and_tool_use_blocks_without_the_reasoning() -> None:
    client = answered(
        {"reasoningContent": {"reasoningText": {"text": "[REDACTED]"}}},
        {"text": "Asking for the left side."},
        {"toolUse": {"toolUseId": "t1", "name": "request_view", "input": {"guidance": "Go left."}}},
        stop_reason="tool_use",
    )

    turn = NovaChatModel(client).respond("s", MESSAGES, TOOLS)

    assert turn == ModelTurn(
        content=[
            {"type": "text", "text": "Asking for the left side."},
            {
                "type": "tool_use",
                "id": "t1",
                "name": "request_view",
                "input": {"guidance": "Go left."},
            },
        ],
        stop_reason="tool_use",
    )


@pytest.mark.parametrize("stop_reason", ["content_filtered", "guardrail_intervened"])
def test_a_filtered_answer_is_a_refusal(stop_reason: str) -> None:
    turn = NovaChatModel(answered(stop_reason=stop_reason)).respond("s", MESSAGES, TOOLS)

    assert turn == ModelTurn(content=[], stop_reason="refusal")


def test_the_call_leaves_the_history_it_was_given_alone() -> None:
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "a"}]},
        {"role": "user", "content": [{"type": "text", "text": "b"}]},
    ]
    before = copy.deepcopy(messages)

    sent_by(messages=messages)

    assert messages == before


def test_an_aws_error_is_a_model_that_is_unavailable() -> None:
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Too many tokens per day"}},
        "Converse",
    )

    with pytest.raises(ModelUnavailable, match="ThrottlingException"):
        NovaChatModel(FakeClient(error)).respond("s", MESSAGES, TOOLS)
