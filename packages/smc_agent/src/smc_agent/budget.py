"""A daily cap on the calls a public deployment makes to its models.

Every call to Bedrock is billed, and a public demo can be called by anyone. The
cap counts the agent's calls and the vision model's together, per UTC day; past
it a call is unavailable, as a model that does not answer is. The agent then
speaks with the policy's own words and its trace records the fallback, so a
session still runs to its end; only the wording and the second look are lost.
"""

import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from smc_agent.model import ChatModel, ModelTurn, ModelUnavailable
from smc_agent.vision import VisionModel


def utc_today() -> date:
    return datetime.now(UTC).date()


class DailyBudget:
    """At most `limit` model calls a UTC day, shared across threads."""

    def __init__(self, limit: int, today: Callable[[], date] = utc_today) -> None:
        if limit < 1:
            raise ValueError("a daily budget allows at least one call")
        self.limit = limit
        self._today = today
        self._day: date | None = None
        self._used = 0
        self._lock = threading.Lock()

    @property
    def used(self) -> int:
        with self._lock:
            return self._used if self._day == self._today() else 0

    def take(self) -> None:
        """Count one call; ModelUnavailable when the day's calls are spent."""
        with self._lock:
            day = self._today()
            if day != self._day:
                self._day, self._used = day, 0
            if self._used >= self.limit:
                raise ModelUnavailable(
                    f"the {self.limit} model calls of {day.isoformat()} are spent"
                )
            self._used += 1


class BudgetedModel:
    """The agent's model, each call taken from the budget first."""

    def __init__(self, model: ChatModel, budget: DailyBudget) -> None:
        self.model = model
        self.budget = budget

    def respond(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        self.budget.take()
        return self.model.respond(system, messages, tools)


class BudgetedVision:
    """The vision model, each look taken from the same budget first."""

    def __init__(self, model: VisionModel, budget: DailyBudget) -> None:
        self.model = model
        self.budget = budget

    def look(self, image: bytes, image_format: str, question: str) -> str:
        self.budget.take()
        return self.model.look(image, image_format, question)
