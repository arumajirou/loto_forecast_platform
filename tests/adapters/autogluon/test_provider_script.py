from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_script_module():
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "run_autogluon_timeseries_provider.py"
    spec = importlib.util.spec_from_file_location("autogluon_provider_script", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_v2_dispatches_to_contract_provider(monkeypatch) -> None:
    module = _load_script_module()
    provider_module = ModuleType("loto.adapters.autogluon.provider")
    provider_module.run_provider_v2 = lambda payload: {
        "schema_version": 2,
        "status": "OK",
        "run_id": payload["run_id"],
    }
    monkeypatch.setitem(sys.modules, "loto.adapters.autogluon.provider", provider_module)

    response = module.run_provider({"schema_version": 2, "run_id": "dispatch-test"})
    assert response == {
        "schema_version": 2,
        "status": "OK",
        "run_id": "dispatch-test",
    }


def test_schema_v1_remains_on_legacy_path(monkeypatch) -> None:
    module = _load_script_module()
    monkeypatch.setattr(
        module,
        "_run_provider_v1",
        lambda payload: {"schema_version": 1, "mode": payload["mode"]},
    )
    response = module.run_provider({"mode": "load_predict"})
    assert response == {"schema_version": 1, "mode": "load_predict"}
