from loto.registry.sqlite import Registry


def test_registry_stage_updates_are_append_only(tmp_path):
    registry = Registry(tmp_path / "registry.sqlite3")
    registry.record_stage("run-1", "INGEST", "SUCCEEDED", {"rows": 10})
    registry.record_stage("run-1", "VALIDATE", "SUCCEEDED", {})
    events = registry.list_stage_events("run-1")
    assert [e["stage"] for e in events] == ["INGEST", "VALIDATE"]
