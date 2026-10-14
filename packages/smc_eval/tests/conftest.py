import pytest
from eval_scene import ENVIRONMENT, SAMPLES, scene_dataset
from smc_agent.contracts import TraceEvent
from smc_eval.dataset import Dataset
from smc_eval.evaluate import evaluate
from smc_eval.results import Results


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    return scene_dataset()


@pytest.fixture(scope="session")
def run(dataset: Dataset) -> tuple[Results, dict[str, list[TraceEvent]]]:
    """One evaluation of the synthetic scene, shared by every test that reads it."""
    return evaluate(
        dataset, evaluated_at="2026-10-14T12:00:00+02:00", environment=ENVIRONMENT, samples=SAMPLES
    )


@pytest.fixture(scope="session")
def results(run: tuple[Results, dict[str, list[TraceEvent]]]) -> Results:
    return run[0]
