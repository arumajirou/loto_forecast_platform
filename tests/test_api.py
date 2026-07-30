from fastapi.testclient import TestClient

from loto.api.app import create_app


def test_health_endpoint(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Loto Trusted Vertical Slice" in dashboard.text
