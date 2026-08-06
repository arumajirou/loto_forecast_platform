from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_provider_module() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "run_tabpfn_ts_v2_certified_provider.py"
    spec = importlib.util.spec_from_file_location("tabpfn_ts_v2_certified_provider", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_request() -> dict[str, object]:
    return {
        "repo_id": "Prior-Labs/TabPFN-v2-reg",
        "revision": "4972a65a1b30806315c6f92499959ffbfc69a673",
        "weight_filename": "tabpfn-v2-regressor.ckpt",
        "local_files_only": True,
        "offline_required": True,
        "telemetry_disabled": True,
        "network_access": False,
        "license_accepted": True,
        "prediction_length": 1,
        "device": "cuda",
        "seed": 1,
    }


def test_certified_provider_requires_license_acceptance() -> None:
    module = _load_provider_module()
    request = _base_request()
    request["license_accepted"] = False
    with pytest.raises(ValueError, match="license acceptance"):
        module._validate_request_identity(request)


def test_certified_provider_requires_offline_execution() -> None:
    module = _load_provider_module()
    request = _base_request()
    request["network_access"] = True
    with pytest.raises(ValueError, match="must be offline"):
        module._validate_request_identity(request)


def test_certified_provider_rejects_untrusted_revision() -> None:
    module = _load_provider_module()
    request = _base_request()
    request["revision"] = "untrusted"
    with pytest.raises(ValueError, match="unsupported revision"):
        module._validate_request_identity(request)


def test_certified_provider_rejects_multi_step_legacy_runtime() -> None:
    module = _load_provider_module()
    request = _base_request()
    request["prediction_length"] = 2
    with pytest.raises(ValueError, match="prediction_length=1"):
        module._validate_request_identity(request)


def test_candidate_frame_has_37_rows_per_draw() -> None:
    module = _load_provider_module()
    history = [
        {
            "draw_date": "2026-01-01",
            "n1": 1,
            "n2": 2,
            "n3": 3,
            "n4": 4,
            "n5": 5,
            "n6": 6,
            "n7": 7,
        }
    ]
    frame = module._build_candidate_frame(history)
    assert len(frame) == 37
    assert frame["target"].sum() == 7.0
