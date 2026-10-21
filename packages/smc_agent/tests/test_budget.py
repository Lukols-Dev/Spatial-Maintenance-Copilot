"""The daily cap on model calls: counted per UTC day, shared by the agent and the vision model."""

from datetime import date
from typing import Any

import pytest
from smc_agent.budget import BudgetedModel, BudgetedVision, DailyBudget
from smc_agent.model import ModelTurn, ModelUnavailable


class Day:
    def __init__(self) -> None:
        self.value = date(2026, 10, 27)

    def __call__(self) -> date:
        return self.value


class Echo:
    """A model and a vision model that answer every call, and count them."""

    def __init__(self) -> None:
        self.calls = 0

    def respond(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelTurn:
        self.calls += 1
        return ModelTurn(content=[], stop_reason="end_turn")

    def look(self, image: bytes, image_format: str, question: str) -> str:
        self.calls += 1
        return "yes"


def test_the_day_s_calls_are_shared_and_the_next_day_starts_again() -> None:
    day = Day()
    budget = DailyBudget(3, today=day)
    inner = Echo()
    agent, vision = BudgetedModel(inner, budget), BudgetedVision(inner, budget)

    agent.respond("system", [], [])
    vision.look(b"jpeg", "jpeg", "a box?")
    agent.respond("system", [], [])
    with pytest.raises(ModelUnavailable, match="the 3 model calls of 2026-10-27 are spent"):
        vision.look(b"jpeg", "jpeg", "a box?")

    assert inner.calls == 3
    assert budget.used == 3
    day.value = date(2026, 10, 28)
    assert budget.used == 0
    agent.respond("system", [], [])
    assert inner.calls == 4


def test_a_budget_allows_at_least_one_call() -> None:
    with pytest.raises(ValueError, match="at least one"):
        DailyBudget(0)
