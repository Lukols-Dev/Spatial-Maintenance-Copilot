"""Amazon Nova 2 Lite on Bedrock, through the Converse API of boto3's bedrock-runtime.

The agent keeps its history in the Messages API's blocks (model.py), so this
adapter translates both ways: the history and the tools into Converse's shapes
on the way out, the answer back into text and tool_use blocks. Nova's
reasoning comes back as "[REDACTED]", so the history keeps nothing of it.

Nova 2 Lite reasons only when asked: effort asks at its level. Nova has three
levels, so xhigh and max ask for high, and at high it takes no inferenceConfig:
it sets its own token limit and temperature.
"""

from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from smc_agent.model import ModelTurn, ModelUnavailable

# The EU profile: in eu-north-1 Nova 2 Lite runs only through eu. or global.
DEFAULT_MODEL_ID = "eu.amazon.nova-2-lite-v1:0"
DEFAULT_EFFORT = "low"
REASONING_EFFORT = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}
# Reasoning and answer together, as AWS advises per level; below them Nova
# fails with "maxTokens is insufficient". Temperature 0 steadies tool calls.
MAX_TOKENS = {"low": 15000, "medium": 30000}
# Converse's stops that mean Nova declined, as the agent reads a refusal.
DECLINED = {"content_filtered", "guardrail_intervened"}


class NovaChatModel:
    """ChatModel over the Converse API: one request per call, nothing kept.

    client is boto3's bedrock-runtime client, or anything with its converse;
    it is typed Any because boto3 has no types.
    """

    def __init__(
        self, client: Any, model_id: str = DEFAULT_MODEL_ID, effort: str = DEFAULT_EFFORT
    ) -> None:
        self.client = client
        self.model_id = model_id
        self.effort = REASONING_EFFORT[effort]

    def respond(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": _messages(messages),
            "toolConfig": {"tools": [_tool(tool) for tool in tools], "toolChoice": {"auto": {}}},
            "additionalModelRequestFields": {
                "reasoningConfig": {"type": "enabled", "maxReasoningEffort": self.effort}
            },
        }
        if self.effort in MAX_TOKENS:
            request["inferenceConfig"] = {"maxTokens": MAX_TOKENS[self.effort], "temperature": 0}
        try:
            response = self.client.converse(**request)
        except (BotoCoreError, ClientError) as error:
            raise ModelUnavailable(f"{type(error).__name__}: {error}") from error
        stop_reason = str(response["stopReason"])
        return ModelTurn(
            content=_answer(response["output"]["message"]["content"]),
            stop_reason="refusal" if stop_reason in DECLINED else stop_reason,
        )


def nova_model(
    region: str,
    model_id: str = DEFAULT_MODEL_ID,
    effort: str = DEFAULT_EFFORT,
    *,
    access_key: str | None,
    secret_key: str | None,
) -> NovaChatModel:
    """The model in this AWS region, called with the keys of an IAM user, or without keys
    with the credentials the platform gives, the ECS task role.

    Ten minutes to read an answer and two retries, as the Anthropic SDK gives
    Claude: boto3's minute is short for reasoning at high.
    """
    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(read_timeout=600, retries={"total_max_attempts": 3}),
    )
    return NovaChatModel(client, model_id, effort)


# ---- the Messages API's blocks and Converse's -----------------------------------------


def _tool(tool: dict[str, Any]) -> dict[str, Any]:
    """A tool of tools.py as a toolSpec. Converse has no strict: Nova decodes within the schema."""
    return {
        "toolSpec": {
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": {"json": tool["input_schema"]},
        }
    }


def _messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The history in Converse's shape, the messages of one role in a row joined.

    Converse wants the roles to alternate. The agent's history can hold two
    user messages in a row (a turn the model did not answer, then the next
    view), which the Messages API reads as one turn, and so does this.
    """
    converted: list[dict[str, Any]] = []
    for message in messages:
        content = message["content"]
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        parts = [part for block in blocks if (part := _part(block)) is not None]
        if not parts:
            continue
        if converted and converted[-1]["role"] == message["role"]:
            converted[-1]["content"].extend(parts)
        else:
            converted.append({"role": message["role"], "content": parts})
    return converted


def _part(block: dict[str, Any]) -> dict[str, Any] | None:
    """One block as Converse takes it: text, a tool call or its result; None for anything else.

    The agent's tool results are text. Empty text and another model's thinking
    have nothing for Nova, and Converse refuses a blank text block.
    """
    match block.get("type"):
        case "text":
            return {"text": block["text"]} if block["text"].strip() else None
        case "tool_use":
            return {
                "toolUse": {
                    "toolUseId": block["id"],
                    "name": block["name"],
                    "input": block["input"],
                }
            }
        case "tool_result":
            return {
                "toolResult": {
                    "toolUseId": block["tool_use_id"],
                    "content": [{"text": block["content"]}],
                    "status": "error" if block.get("is_error") else "success",
                }
            }
        case _:
            return None


def _answer(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nova's answer as the Messages API's blocks: its text and its tool calls, in order."""
    blocks: list[dict[str, Any]] = []
    for part in content:
        if "toolUse" in part:
            call = part["toolUse"]
            blocks.append(
                {
                    "type": "tool_use",
                    "id": call["toolUseId"],
                    "name": call["name"],
                    "input": call["input"],
                }
            )
        elif str(part.get("text", "")).strip():
            blocks.append({"type": "text", "text": part["text"]})
    return blocks
