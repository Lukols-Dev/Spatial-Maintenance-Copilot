"""The second look: what goes to Converse with the image, and what of the answer is kept.

A fake client stands for boto3's bedrock-runtime. Nothing here reaches AWS.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest
from botocore.exceptions import ClientError
from smc_agent.model import ModelUnavailable
from smc_agent.vision import SYSTEM, NovaVision, NoVision, look


@dataclass
class FakeClient:
    answer: str = "Yes. A cardboard box sits on the shelf."
    calls: list[dict[str, Any]] = field(default_factory=list)
    error: Exception | None = None

    def converse(self, **request: Any) -> dict[str, Any]:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return {"output": {"message": {"role": "assistant", "content": [{"text": self.answer}]}}}


def test_the_image_and_the_question_go_in_one_message() -> None:
    client = FakeClient()

    NovaVision(client, "eu.amazon.nova-2-lite-v1:0").look(b"jpeg", "jpeg", "Is the box there?")

    request = client.calls[0]
    assert request["modelId"] == "eu.amazon.nova-2-lite-v1:0"
    assert request["system"] == [{"text": SYSTEM}]
    content = request["messages"][0]["content"]
    assert content[0] == {"image": {"format": "jpeg", "source": {"bytes": b"jpeg"}}}
    assert content[1] == {"text": "Is the box there?"}
    assert "reasoningConfig" not in str(request)


@pytest.mark.parametrize(
    ("answer", "verdict"),
    [
        ("Yes. A cardboard box sits on the shelf.", "yes"),
        ("no, the shelf is empty", "no"),
        ("Possibly a box, hard to tell.", "unclear"),
        ("", "unclear"),
    ],
)
def test_the_answer_starts_with_its_verdict(answer: str, verdict: str) -> None:
    found = look(NovaVision(FakeClient(answer=answer), "m"), b"x", "jpeg", "?")

    assert found.verdict == verdict
    assert found.answer == answer


def test_an_answer_with_numbers_keeps_only_its_yes_or_no() -> None:
    found = look(
        NovaVision(FakeClient(answer="Yes, about 90% sure, 15 cm wide."), "m"), b"x", "jpeg", "?"
    )

    assert (found.verdict, found.answer) == ("yes", "Yes.")


def test_no_answer_is_unavailable() -> None:
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse"
    )

    with pytest.raises(ModelUnavailable, match="ClientError"):
        look(NovaVision(FakeClient(error=error), "m"), b"x", "jpeg", "?")
    with pytest.raises(ModelUnavailable, match="not configured"):
        look(NoVision("not configured"), b"x", "jpeg", "?")
