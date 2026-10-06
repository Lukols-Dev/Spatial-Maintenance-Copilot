"""The web app's examples of the API's JSON are what the service sends and accepts.

apps/web/lib/api-examples/ holds one example per model; the web app's tests use
them as mocks of the service. Each must validate against its pydantic model
and read back field for field, so a renamed or added field breaks a test on
whichever side changed first.
"""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel
from smc_perception.models import (
    AtlasBuildRequest,
    AtlasDetail,
    Board,
    BoardMeasurement,
    ClicksSummary,
    ViewSet,
    ViewSetSummary,
    Workspace,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "apps/web/lib/api-examples"
MODELS: dict[str, type[BaseModel]] = {
    "workspace.json": Workspace,
    "workspace-empty.json": Workspace,
    "view-set.json": ViewSet,
    "view-set-summary.json": ViewSetSummary,
    "clicks-summary.json": ClicksSummary,
    "board.json": Board,
    "board-measurement.json": BoardMeasurement,
    "atlas.json": AtlasDetail,
    "atlas-build-request.json": AtlasBuildRequest,
}


def test_every_example_has_a_model() -> None:
    examples = sorted(path.name for path in EXAMPLES.glob("*.json"))

    assert examples == sorted(MODELS)


@pytest.mark.parametrize("name", sorted(MODELS))
def test_an_example_is_valid_json_of_its_model(name: str) -> None:
    text = (EXAMPLES / name).read_text(encoding="utf-8")

    model = MODELS[name].model_validate_json(text)

    assert model.model_dump(mode="json", exclude_unset=True) == json.loads(text)
