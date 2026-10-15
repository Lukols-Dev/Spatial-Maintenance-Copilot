"""Claude on Amazon Bedrock, through the Anthropic SDK's Bedrock client.

Claude Opus 5.5 thinks on every request and a request may not turn that off,
so effort is the one control of how long a turn takes. tool_choice stays auto:
this model refuses a forced tool, and the agent asks again when no tool came.
"""

from typing import Any

import anthropic

from smc_agent.model import ModelTurn, ModelUnavailable

DEFAULT_MODEL_ID = "anthropic.claude-opus-5-5"
DEFAULT_EFFORT = "low"
MAX_TOKENS = 8000


class BedrockChatModel:
    """ChatModel over a Messages API client: one request per call, nothing kept.

    client is anthropic.AnthropicBedrockMantle, or anything with its
    messages.create; it is typed Any because the SDK overloads that method.
    """

    def __init__(
        self,
        client: Any,
        model_id: str = DEFAULT_MODEL_ID,
        effort: str = DEFAULT_EFFORT,
        max_tokens: int = MAX_TOKENS,
    ) -> None:
        self.client = client
        self.model_id = model_id
        self.effort = effort
        self.max_tokens = max_tokens

    def respond(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        try:
            response = self.client.messages.create(
                model=self.model_id,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
                tools=tools,
                tool_choice={"type": "auto"},
                output_config={"effort": self.effort},
            )
        except anthropic.APIError as error:
            raise ModelUnavailable(f"{type(error).__name__}: {error}") from error
        return ModelTurn(
            content=[block.to_dict() for block in response.content],
            stop_reason=str(response.stop_reason),
        )


def bedrock_model(
    region: str,
    model_id: str = DEFAULT_MODEL_ID,
    effort: str = DEFAULT_EFFORT,
    *,
    access_key: str | None,
    secret_key: str | None,
) -> BedrockChatModel:
    """The model in this AWS region, called with the keys of an IAM user, or the platform's credentials."""
    client = anthropic.AnthropicBedrockMantle(
        aws_region=region, aws_access_key=access_key, aws_secret_key=secret_key
    )
    return BedrockChatModel(client, model_id, effort)
