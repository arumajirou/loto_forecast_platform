import pytest

from loto.registry.full import PlatformRegistry


def test_registry_run_task_forecast_and_two_person_approval(tmp_path):
    reg = PlatformRegistry(tmp_path / "platform.sqlite3")
    reg.create_run("run-1", config_hash="abc")
    reg.update_run("run-1", status="RUNNING", current_stage="INGEST")
    reg.record_task("run-1", "INGEST", "SUCCEEDED", output_uri="file:///x")
    assert reg.completed_stages("run-1") == {"INGEST"}
    reg.register_forecast("f-1", "run-1", "loto7-1", {"payload": {}}, True)
    reg.score_forecast("f-1", {"hits_at_7": 2})
    assert reg.list_rows("forecasts")[0]["status"] == "SCORED"
    reg.request_approval("release", "r-1", "promote", "alice", "quality gates passed")
    with pytest.raises(PermissionError):
        reg.decide_approval("release", "r-1", "promote", "alice", True)
    reg.decide_approval("release", "r-1", "promote", "bob", True)
    assert reg.list_rows("approvals")[0]["status"] == "APPROVED"
