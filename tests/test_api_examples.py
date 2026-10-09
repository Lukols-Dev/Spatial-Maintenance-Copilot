"""The web app's examples of the API's JSON are what the service sends and accepts.

apps/web/lib/api-examples/ holds one example per model; the web app's tests use
them as mocks of the service. Each must validate against its pydantic model
and read back field for field, so a renamed or added field breaks a test on
whichever side changed first.

The localise results are more than shapes: the service rebuilds each of them
from its inputs, so the numbers the web app is tested with are the numbers
it will get.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import cv2 as cv
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from smc_perception.main import app
from smc_perception.models import (
    AtlasBuildRequest,
    AtlasDetail,
    Board,
    BoardMeasurement,
    ClicksSummary,
    LocaliseRequest,
    LocaliseResult,
    ViewSet,
    ViewSetSummary,
    Workspace,
)

REPOSITORY = Path(__file__).resolve().parents[1]
EXAMPLES = REPOSITORY / "apps/web/lib/api-examples"
MODELS: dict[str, type[BaseModel]] = {
    "workspace.json": Workspace,
    "workspace-empty.json": Workspace,
    "workspace-locate.json": Workspace,
    "view-set.json": ViewSet,
    "view-set-viewpoints.json": ViewSet,
    "view-set-summary.json": ViewSetSummary,
    "clicks-summary.json": ClicksSummary,
    "board.json": Board,
    "board-measurement.json": BoardMeasurement,
    "atlas.json": AtlasDetail,
    "atlas-cabinet.json": AtlasDetail,
    "atlas-build-request.json": AtlasBuildRequest,
    "localise-request.json": LocaliseRequest,
    "localise-result.json": LocaliseResult,
    "localise-result-reliable.json": LocaliseResult,
    "localise-result-failure.json": LocaliseResult,
}


def example(name: str) -> Any:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_every_example_has_a_model() -> None:
    examples = sorted(path.name for path in EXAMPLES.glob("*.json"))

    assert examples == sorted(MODELS)


@pytest.mark.parametrize("name", sorted(MODELS))
def test_an_example_is_valid_json_of_its_model(name: str) -> None:
    text = (EXAMPLES / name).read_text(encoding="utf-8")

    model = MODELS[name].model_validate_json(text)

    assert model.model_dump(mode="json", exclude_unset=True) == json.loads(text)


# ---- the localise examples, rebuilt by the service ------------------------------


@pytest.fixture
def cabinet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The workspace the localise examples come from.

    The repository's iPhone calibration, the cabinet atlas, and the test view
    set: blank images, since localising reads only their size and the clicks.
    """
    root = tmp_path / "workspace"
    calibration = REPOSITORY / "calib/intrinsics/iphone11-1x-1080p-portrait.yml"
    (root / "calib" / "intrinsics").mkdir(parents=True)
    shutil.copy(calibration, root / "calib" / "intrinsics" / calibration.name)

    atlas = example("atlas-cabinet.json")["atlas"]
    (root / "data" / "atlas").mkdir(parents=True)
    (root / "data" / "atlas" / f"{atlas['asset_id']}.json").write_text(json.dumps(atlas))

    view_set = example("view-set-viewpoints.json")
    folder = root / "data" / "views" / view_set["name"]
    folder.mkdir(parents=True)
    for image in view_set["images"]:
        blank = np.zeros((image["height"], image["width"], 3), np.uint8)
        assert cv.imwrite(str(folder / image["file"]), blank)
    (folder / "clicks.json").write_text(json.dumps(view_set["clicks"]))

    monkeypatch.setenv("SMC_WORKSPACE", str(root))
    monkeypatch.delenv("SMC_READ_ONLY", raising=False)
    return TestClient(app)


def assert_close(actual: Any, expected: Any, rel: float, abs_: float, where: str = "") -> None:
    """Equal JSON, numbers within rel (or abs_ near zero), everything else exactly."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), where
        assert actual.keys() == expected.keys(), where
        for key, value in expected.items():
            assert_close(actual[key], value, rel, abs_, f"{where}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), where
        assert len(actual) == len(expected), where
        for index, (got, value) in enumerate(zip(actual, expected, strict=True)):
            assert_close(got, value, rel, abs_, f"{where}[{index}]")
    elif isinstance(expected, int | float) and not isinstance(expected, bool):
        assert actual == pytest.approx(expected, rel=rel, abs=abs_), where
    else:
        assert actual == expected, where


def assert_same_result(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """The service's answer is the example.

    The localisation and the decision agree to 1e-6 relative; abs 1e-9 only
    matters for numbers near zero, such as a rotation component, which another
    platform's floating point may move further than 1e-6 of themselves. The
    example rounds projections and the truth error to 0.01 px.
    """
    assert actual.keys() == expected.keys()
    for key in ("request", "camera_id", "image", "observations", "ignored_points"):
        assert actual[key] == expected[key], key
    for key in ("localisation", "decision"):
        assert_close(actual[key], expected[key], 1e-6, 1e-9, key)
    for key in ("projections", "truth"):
        assert_close(actual[key], expected[key], 0.0, 0.005, key)


@pytest.mark.parametrize(
    "name",
    ["localise-result.json", "localise-result-reliable.json", "localise-result-failure.json"],
)
def test_a_localise_example_is_what_the_service_answers(cabinet: TestClient, name: str) -> None:
    expected = example(name)

    response = cabinet.post("/localise", json=expected["request"])

    assert response.status_code == 200, response.text
    assert_same_result(response.json(), expected)


def test_the_request_example_gets_the_result_example(cabinet: TestClient) -> None:
    """Without a sigma, an atlas without a build report gets 2 px; that is the example."""
    response = cabinet.post("/localise", json=example("localise-request.json"))

    assert response.status_code == 200, response.text
    assert_same_result(response.json(), example("localise-result.json"))
