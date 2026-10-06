from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from smc_perception.main import allowed_origins, app


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
