from fastapi.testclient import TestClient
from smc_perception.main import app

client = TestClient(app)


def test_helth_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
