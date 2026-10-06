from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from smc_perception.main import app
from workspace_builder import write_calibration, write_rig


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty workspace the service is pointed at, writable."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("SMC_WORKSPACE", str(workspace))
    monkeypatch.delenv("SMC_READ_ONLY", raising=False)
    return workspace


@pytest.fixture
def client(root: Path) -> TestClient:
    return TestClient(app)


@pytest.fixture
def calib(root: Path) -> Path:
    """The synthetic phone's calibration and the rig file, its rig boards unmeasured."""
    write_calibration(root)
    write_rig(root)
    return root


@pytest.fixture
def read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMC_READ_ONLY", "true")
