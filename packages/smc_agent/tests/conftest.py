import pytest
from agent_scene import FakePerception
from langgraph.checkpoint.memory import InMemorySaver


@pytest.fixture
def perception() -> FakePerception:
    return FakePerception()


@pytest.fixture
def saver() -> InMemorySaver:
    """One store for every Copilot of a test: two of them stand for two requests."""
    return InMemorySaver()
