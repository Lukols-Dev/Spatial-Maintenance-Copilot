from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smc_perception.main import allowed_origins, app
from workspace_builder import write_view_set


def test_allowed_origins_defaults_to_the_local_web_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    assert allowed_origins() == ["http://localhost:3000"]


def test_allowed_origins_reads_a_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS", "https://d1234.cloudfront.net, http://localhost:3000,"
    )

    assert allowed_origins() == ["https://d1234.cloudfront.net", "http://localhost:3000"]


def test_the_local_web_server_may_call_the_api() -> None:
    response = TestClient(app).get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_the_local_web_server_may_send_a_put() -> None:
    response = TestClient(app).options(
        "/view-sets/cabinet/clicks",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_a_refused_write_can_be_read_by_the_web_page(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMC_READ_ONLY", "1")

    response = TestClient(app).put(
        "/view-sets/cabinet/clicks",
        json={"camera_id": "", "views": {}},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_a_failure_the_service_did_not_foresee_can_be_read_by_the_web_page(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full disk while saving clicks: the page must hear that, not that the service is gone."""
    write_view_set(root, "cabinet", {"a.png": (40, 30)})

    def full_disk(path: Path, _data: bytes) -> None:
        raise OSError(28, "No space left on device", str(path))

    monkeypatch.setattr("smc_perception.view_sets.write_atomic", full_disk)

    def save(client: TestClient) -> Any:
        return client.put(
            "/view-sets/cabinet/clicks",
            json={"camera_id": "", "views": {}},
            headers={"Origin": "http://localhost:3000"},
        )

    response = save(TestClient(app, raise_server_exceptions=False))

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.json() == {"detail": "internal error: OSError (No space left on device)"}
    assert str(root) not in response.text
    # The error still reaches the server, which logs it with its traceback.
    with pytest.raises(OSError, match="No space left on device"):
        save(TestClient(app))
