"""A second look with a vision-language model: words about what a region shows, never geometry.

The geometry says where the target is; once the panel in front of it is open,
the model is shown that region and asked whether the target is there. Its
answer is a second opinion beside the measurement, never a replacement for it:
it moves nothing and accepts nothing. Like the agent's words, it carries no
numbers, so a confidence figure or a position never comes from the model.
"""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from smc_agent.model import ModelUnavailable
from smc_agent.wording import has_numbers

Verdict = Literal["yes", "no", "unclear"]

SYSTEM = (
    "You look at one region of a photo taken during maintenance. Answer the question about it: "
    "start with yes or no, then one short sentence on what you see. Never give numbers, "
    "measurements, positions or confidence figures."
)


class VisionModel(Protocol):
    def look(self, image: bytes, image_format: str, question: str) -> str: ...


@dataclass(frozen=True)
class Look:
    """What the model said about a region, and the yes or no it starts with."""

    verdict: Verdict
    answer: str


class NoVision:
    """The vision model when none is configured: every look is unavailable."""

    def __init__(self, why: str) -> None:
        self.why = why

    def look(self, image: bytes, image_format: str, question: str) -> str:
        raise ModelUnavailable(self.why)


class NovaVision:
    """VisionModel over the Converse API: the image and the question in one message, nothing kept."""

    def __init__(self, client: Any, model_id: str) -> None:
        self.client = client
        self.model_id = model_id

    def look(self, image: bytes, image_format: str, question: str) -> str:
        try:
            response = self.client.converse(
                modelId=self.model_id,
                system=[{"text": SYSTEM}],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"image": {"format": image_format, "source": {"bytes": image}}},
                            {"text": question},
                        ],
                    }
                ],
                inferenceConfig={"maxTokens": 300, "temperature": 0},
            )
        except (BotoCoreError, ClientError) as error:
            raise ModelUnavailable(f"{type(error).__name__}: {error}") from error
        texts = [
            part["text"] for part in response["output"]["message"]["content"] if "text" in part
        ]
        return " ".join(text.strip() for text in texts if text.strip())


def look(model: VisionModel, image: bytes, image_format: str, question: str) -> Look:
    """The model's answer about the image, held to words: one with numbers keeps only its yes or no.

    Raises ModelUnavailable when the model gives no answer.
    """
    answer = model.look(image, image_format, question).strip()
    first = answer.split(maxsplit=1)[0].strip(".,:;!").lower() if answer else ""
    verdict: Verdict = "yes" if first == "yes" else "no" if first == "no" else "unclear"
    if has_numbers(answer):
        answer = {"yes": "Yes.", "no": "No.", "unclear": ""}[verdict]
    return Look(verdict=verdict, answer=answer)
