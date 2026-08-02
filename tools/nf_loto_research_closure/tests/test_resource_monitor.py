from src.monitoring.resource_monitor import collect_resource_snapshot


def test_collect_resource_snapshot_has_basic_keys():
    snap = collect_resource_snapshot()
    assert isinstance(snap, dict)
    # 最低限、CPU / memory / disk 情報が含まれていること
    assert "cpu" in snap
    assert "memory" in snap
    assert "disk" in snap
    assert "timestamp" in snap
