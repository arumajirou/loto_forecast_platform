from __future__ import annotations

from fastapi.testclient import TestClient

from loto.probabilistic.api import create_app


class FakeManager:
    def profiles(self):
        return [{"profile": "fast_gpu", "available": True}]

    def current(self):
        return {"run_id": "api-test", "status": "RUNNING"}

    def list_runs(self, limit=50):
        return [{"run_id": "api-test", "status": "RUNNING"}]

    def status(self, run_id):
        if run_id != "api-test":
            raise KeyError(run_id)
        return {
            "run_id": run_id,
            "status": "RUNNING",
            "progress": {"progress_percent": 25.0},
        }

    def start(self, request):
        return {
            "run_id": request.run_id or "api-test",
            "status": "RUNNING",
            "profile": request.profile,
        }

    def stop(self, run_id, force=False):
        return {"run_id": run_id, "status": "STOPPED", "force": force}

    def log(self, run_id, lines=200):
        return "test log"

    def preflight(self, profile):
        return {"passed": True, "profile": profile}

    def test_notifications(self, request):
        return {"status": "PASS", "speech": request.speech, "email": request.email}


def test_health_is_public_and_api_requires_token(tmp_path):
    client = TestClient(create_app(tmp_path, manager=FakeManager(), token="secret"))
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/profiles").status_code == 401
    response = client.get(
        "/api/v1/profiles",
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    assert response.json()[0]["profile"] == "fast_gpu"


def test_start_status_stop_and_log(tmp_path):
    client = TestClient(create_app(tmp_path, manager=FakeManager(), token="secret"))
    headers = {"Authorization": "Bearer secret"}
    response = client.post(
        "/api/v1/runs",
        headers=headers,
        json={"profile": "fast_gpu", "run_id": "api-test", "preflight": False},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "RUNNING"
    assert client.get("/api/v1/runs/current", headers=headers).status_code == 200
    assert client.get("/api/v1/runs/api-test/log", headers=headers).text == "test log"
    stopped = client.post(
        "/api/v1/runs/api-test/stop",
        headers=headers,
        json={"force": False},
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "STOPPED"


def test_preflight_and_notification_test(tmp_path):
    client = TestClient(create_app(tmp_path, manager=FakeManager(), token="secret"))
    headers = {"Authorization": "Bearer secret"}
    assert (
        client.post("/api/v1/preflight", headers=headers, json={"profile": "fast_gpu"}).json()[
            "passed"
        ]
        is True
    )
    assert (
        client.post(
            "/api/v1/notifications/test",
            headers=headers,
            json={"speech": True, "email": False},
        ).json()["status"]
        == "PASS"
    )


def test_voicevox_tts_endpoints(tmp_path, monkeypatch):
    import loto.probabilistic.api as api_module

    client = TestClient(create_app(tmp_path, manager=FakeManager(), token="secret"))
    headers = {"Authorization": "Bearer secret"}
    wav = b"RIFF" + b"\x00" * 64

    monkeypatch.setattr(api_module, "_voicevox_synthesize", lambda request: wav)
    monkeypatch.setattr(api_module, "_play_wav", lambda audio: "paplay")
    monkeypatch.setattr(
        api_module,
        "_voicevox_get_json",
        lambda path, timeout=10.0: "0.25.2" if path == "/version" else [{"name": "test"}],
    )

    assert client.get("/api/v1/tts/status", headers=headers).json()["status"] == "PASS"
    assert client.get("/api/v1/tts/speakers", headers=headers).status_code == 200

    response = client.post(
        "/api/v1/tts/synthesize",
        headers=headers,
        json={"text": "進捗は25パーセントです", "speaker": 3, "speed_scale": 1.1},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == wav

    played = client.post(
        "/api/v1/tts/play",
        headers=headers,
        json={"text": "音声再生テストです", "speaker": 3},
    )
    assert played.status_code == 200
    assert played.json()["player"] == "paplay"
