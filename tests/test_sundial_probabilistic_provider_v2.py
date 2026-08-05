from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_runner() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_sundial_provider.py"
    spec = importlib.util.spec_from_file_location("sundial_runner_v2", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()


def _install_provider_import_stubs() -> None:
    base = ModuleType("loto.models.providers.base")

    class FoundationProviderError(RuntimeError):
        def __init__(self, status: str, message: str):
            super().__init__(message)
            self.status = status

    class FoundationProvider:
        def inspect_properties(self) -> dict[str, Any]:
            return {}

    base.FoundationProvider = FoundationProvider
    base.FoundationProviderError = FoundationProviderError
    subprocess_module = ModuleType("loto.models.providers.subprocess")

    class SubprocessProviderContractError(ValueError):
        def __init__(self, status: str, message: str):
            super().__init__(message)
            self.status = status

    subprocess_module.SubprocessProviderContractError = SubprocessProviderContractError
    subprocess_module.validate_provider_request = lambda request: None
    subprocess_module.validate_provider_response = lambda response, expected_shape: None
    sys.modules.setdefault("loto", ModuleType("loto"))
    sys.modules.setdefault("loto.models", ModuleType("loto.models"))
    sys.modules.setdefault("loto.models.providers", ModuleType("loto.models.providers"))
    sys.modules["loto.models.providers.base"] = base
    sys.modules["loto.models.providers.subprocess"] = subprocess_module


def _load_adapter() -> ModuleType:
    _install_provider_import_stubs()
    path = PROJECT_ROOT / "src" / "loto" / "models" / "providers" / "sundial.py"
    spec = importlib.util.spec_from_file_location("sundial_adapter_v2", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = _load_adapter()


def _response(
    *,
    num_samples: int = 3,
    requested_device: str = "cpu",
    point_strategy: str = "median",
) -> dict[str, Any]:
    samples = np.arange(7 * num_samples, dtype=float).reshape(7, num_samples, 1)
    mean = np.mean(samples, axis=1)
    median = np.median(samples, axis=1)
    std = np.std(samples, axis=1)
    levels = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
    quantile_array = np.quantile(samples, levels, axis=1)
    quantiles = {
        ADAPTER._quantile_key(level): quantile_array[index].tolist()
        for index, level in enumerate(levels)
    }
    selected = {"mean": mean, "median": median}[point_strategy]
    gpu_used = requested_device == "cuda"
    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 2,
        "predictions": selected[:, 0].tolist(),
        "prediction_shape": [7],
        "finite": True,
        "samples": samples.tolist(),
        "samples_shape": [7, num_samples, 1],
        "sample_statistics": {
            "mean": mean.tolist(),
            "median": median.tolist(),
            "std": std.tolist(),
        },
        "point_forecasts": {
            "mean": mean.tolist(),
            "median": median.tolist(),
        },
        "point_strategy": point_strategy,
        "quantiles": quantiles,
        "quantile_levels": list(levels),
        "quantile_source": "EMPIRICAL_FROM_GENERATED_SAMPLES",
        "properties": {
            "license": "apache-2.0",
            "weight_sha256": {"model.safetensors": "a" * 64},
            "config_sha256": "b" * 64,
            "remote_code_sha256": {"modeling_sundial.py": "c" * 64},
            "loaded_from_resolved_snapshot": True,
            "offline_mode": True,
        },
        "gpu_evidence": {
            "requested_device": requested_device,
            "execution_device": requested_device,
            "gpu_used": gpu_used,
            "cpu_fallback": False,
        },
        "artifact_reference": {
            "repo_id": "thuml/sundial-base-128m",
            "revision": "3212e42564493f520593e5414af4367fc4b49226",
            "snapshot_path": "/tmp/synthetic-snapshot",
        },
    }


def test_quantile_levels_are_strict_and_bounded() -> None:
    assert RUNNER._normalize_quantile_levels([0.1, 0.5, 0.9]) == (0.1, 0.5, 0.9)
    with pytest.raises(RUNNER.SundialProviderRuntimeError):
        RUNNER._normalize_quantile_levels([0.5, 0.5])
    with pytest.raises(RUNNER.SundialProviderRuntimeError):
        RUNNER._normalize_quantile_levels([-0.1, 0.5])


def test_sample_summary_preserves_series_sample_horizon_shape() -> None:
    raw = np.arange(2 * 3 * 1, dtype=float).reshape(2, 3, 1)
    samples = RUNNER._normalize_samples(
        raw,
        expected_series_count=2,
        expected_num_samples=3,
        expected_horizon=1,
    )
    statistics, quantiles = RUNNER._summarize_samples(samples, (0.1, 0.5, 0.9))
    assert np.asarray(statistics["mean"]).shape == (2, 1)
    assert np.asarray(statistics["median"]).shape == (2, 1)
    assert np.asarray(statistics["std"]).shape == (2, 1)
    assert list(quantiles) == ["q0.1", "q0.5", "q0.9"]


def test_non_finite_and_wrong_sample_shapes_fail_closed() -> None:
    with pytest.raises(RUNNER.SundialProviderRuntimeError):
        RUNNER._normalize_samples(
            np.zeros((7, 1)),
            expected_series_count=7,
            expected_num_samples=1,
            expected_horizon=1,
        )
    bad = np.zeros((7, 1, 1))
    bad[0, 0, 0] = np.nan
    with pytest.raises(RUNNER.SundialProviderRuntimeError):
        RUNNER._normalize_samples(
            bad,
            expected_series_count=7,
            expected_num_samples=1,
            expected_horizon=1,
        )


def test_remote_code_allowlist_rejects_unreviewed_or_changed_files(tmp_path: Path) -> None:
    approved: dict[str, str] = {}
    for name in RUNNER.REQUIRED_REMOTE_CODE_FILES:
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        approved[name] = hashlib.sha256(name.encode()).hexdigest()
    assert RUNNER._verify_remote_code(tmp_path, approved) == approved

    unexpected = tmp_path / "unexpected.py"
    unexpected.write_text("pass", encoding="utf-8")
    with pytest.raises(RUNNER.SundialProviderRuntimeError):
        RUNNER._verify_remote_code(tmp_path, approved)
    unexpected.unlink()

    changed = tmp_path / "modeling_sundial.py"
    changed.write_text("changed", encoding="utf-8")
    with pytest.raises(RUNNER.SundialProviderRuntimeError):
        RUNNER._verify_remote_code(tmp_path, approved)


def test_remote_code_review_loader_requires_approved_identity(tmp_path: Path) -> None:
    review = {
        "model_id": "sundial-base",
        "repo_id": "thuml/sundial-base-128m",
        "revision": "3212e42564493f520593e5414af4367fc4b49226",
        "review_status": "APPROVED",
        "files": [{"name": "modeling_sundial.py", "sha256": "a" * 64}],
    }
    path = tmp_path / "remote-code-review.json"
    path.write_text(json.dumps(review), encoding="utf-8")
    assert ADAPTER._load_remote_code_allowlist(path) == {
        "modeling_sundial.py": "a" * 64
    }
    review["review_status"] = "PENDING"
    path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(ADAPTER.FoundationProviderError):
        ADAPTER._load_remote_code_allowlist(path)


def test_valid_distribution_response_passes() -> None:
    response = _response()
    predictions = ADAPTER.validate_sundial_distribution_response(
        response,
        expected_series_count=7,
        expected_num_samples=3,
        expected_horizon=1,
        quantile_levels=ADAPTER.DEFAULT_QUANTILE_LEVELS,
        point_strategy="median",
        requested_device="cpu",
    )
    assert predictions.shape == (7,)


def test_distribution_response_rejects_sample_shape_and_crossing() -> None:
    response = _response()
    response["samples_shape"] = [7, 2, 1]
    with pytest.raises(ADAPTER.FoundationProviderError):
        ADAPTER.validate_sundial_distribution_response(
            response,
            expected_series_count=7,
            expected_num_samples=3,
            expected_horizon=1,
            quantile_levels=ADAPTER.DEFAULT_QUANTILE_LEVELS,
            point_strategy="median",
            requested_device="cpu",
        )

    response = _response()
    response["quantiles"]["q0.9"] = response["quantiles"]["q0.1"]
    response["quantiles"]["q0.75"] = np.full((7, 1), 999.0).tolist()
    with pytest.raises(ADAPTER.FoundationProviderError):
        ADAPTER.validate_sundial_distribution_response(
            response,
            expected_series_count=7,
            expected_num_samples=3,
            expected_horizon=1,
            quantile_levels=ADAPTER.DEFAULT_QUANTILE_LEVELS,
            point_strategy="median",
            requested_device="cpu",
        )


def test_cuda_request_rejects_cpu_fallback() -> None:
    response = _response(requested_device="cuda")
    response["gpu_evidence"]["execution_device"] = "cpu"
    response["gpu_evidence"]["gpu_used"] = False
    response["gpu_evidence"]["cpu_fallback"] = True
    with pytest.raises(ADAPTER.FoundationProviderError) as exc_info:
        ADAPTER.validate_sundial_distribution_response(
            response,
            expected_series_count=7,
            expected_num_samples=3,
            expected_horizon=1,
            quantile_levels=ADAPTER.DEFAULT_QUANTILE_LEVELS,
            point_strategy="median",
            requested_device="cuda",
        )
    assert exc_info.value.status == "CPU_FALLBACK_FORBIDDEN"


def test_legacy_predict_returns_selected_horizon_one_point(monkeypatch: Any) -> None:
    provider = object.__new__(ADAPTER.SundialProvider)
    response = _response(point_strategy="mean")
    monkeypatch.setattr(provider, "predict_distribution", lambda history: response)
    history = pd.DataFrame({f"n{index}": [index] for index in range(1, 8)})
    prediction = provider.predict(history)
    assert prediction.shape == (7,)
    assert np.array_equal(prediction, np.asarray(response["predictions"]))
