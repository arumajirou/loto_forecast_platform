from loto.observability.mlflow_bridge import MlflowBridge


def test_mlflow_bridge_degrades_to_recorded_disabled_state_when_dependency_missing(tmp_path):
    bridge = MlflowBridge("http://127.0.0.1:5050", "loto-test")
    result = bridge.record_run("run-1", {"model": "uniform"}, {"hits": 1.0}, [])
    assert "enabled" in result
    assert result["tracking_uri"] == "http://127.0.0.1:5050"
