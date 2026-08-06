from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    path = ROOT / "scripts" / "verify_sundial_provider_v2_semantics.py"
    spec = importlib.util.spec_from_file_location("sundial_semantic_verifier", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFIER = _load()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _response(snapshot: Path, count: int = 3) -> dict[str, Any]:
    samples = np.arange(7 * count, dtype=float).reshape(7, count, 1)
    levels = [0.05, 0.5, 0.95]
    quantile_array = np.quantile(samples, levels, axis=1)
    statistics = {
        "mean": np.mean(samples, axis=1).tolist(),
        "median": np.median(samples, axis=1).tolist(),
        "std": np.std(samples, axis=1, ddof=0).tolist(),
    }
    return {
        "status": "OK",
        "provider_version": 2,
        "repo_id": VERIFIER.REPO_ID,
        "revision": VERIFIER.REVISION,
        "snapshot_path": str(snapshot),
        "samples_shape": [7, count, 1],
        "samples": samples.tolist(),
        "sample_statistics": statistics,
        "point_forecasts": {
            "mean": statistics["mean"],
            "median": statistics["median"],
        },
        "point_strategy": "median",
        "predictions": np.median(samples, axis=1)[:, 0].tolist(),
        "prediction_shape": [7],
        "finite": True,
        "quantile_levels": levels,
        "quantiles": {
            VERIFIER.quantile_key(level): quantile_array[index].tolist()
            for index, level in enumerate(levels)
        },
        "quantile_source": "EMPIRICAL_FROM_GENERATED_SAMPLES",
        "properties": {
            "config_sha256": VERIFIER.EXPECTED_CONFIG_SHA256,
            "weight_sha256": VERIFIER.EXPECTED_WEIGHT_SHA256,
            "remote_code_sha256": VERIFIER.EXPECTED_REMOTE_CODE_SHA256,
            "num_samples": count,
            "quantile_levels": levels,
            "point_strategy": "median",
        },
        "artifact_reference": {
            "repo_id": VERIFIER.REPO_ID,
            "revision": VERIFIER.REVISION,
            "snapshot_path": str(snapshot),
        },
    }


def _snapshot(tmp_path: Path) -> Path:
    snapshot = tmp_path / VERIFIER.REVISION
    _write(snapshot / "config.json", b"config")
    _write(snapshot / "generation_config.json", b"generation")
    _write(snapshot / "model.safetensors", b"weights")
    for name in VERIFIER.EXPECTED_REMOTE_CODE_SHA256:
        _write(snapshot / name, name.encode())
    return snapshot


def test_valid_response_semantics_pass(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    response = _response(snapshot)
    assert VERIFIER.verify_response(response, snapshot) == []


def test_statistics_and_quantiles_are_recomputed(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    response = _response(snapshot)
    response["sample_statistics"]["mean"][0][0] += 1.0
    response["quantiles"]["q0.5"][0][0] += 1.0
    reasons = VERIFIER.verify_response(response, snapshot)
    assert "SAMPLE_STATISTIC_MISMATCH:mean" in reasons
    assert "QUANTILE_VALUE_MISMATCH:q0.5" in reasons


def test_selected_point_is_recomputed(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    response = _response(snapshot)
    response["predictions"][0] += 1.0
    reasons = VERIFIER.verify_response(response, snapshot)
    assert "SELECTED_POINT_MISMATCH" in reasons


def test_snapshot_hash_and_file_set_are_pinned(tmp_path: Path, monkeypatch: Any) -> None:
    snapshot = _snapshot(tmp_path)
    expected_hashes = {
        "config.json": VERIFIER.sha256(snapshot / "config.json"),
        "generation_config.json": VERIFIER.sha256(snapshot / "generation_config.json"),
        "model.safetensors": VERIFIER.sha256(snapshot / "model.safetensors"),
    }
    monkeypatch.setattr(VERIFIER, "EXPECTED_CONFIG_SHA256", expected_hashes["config.json"])
    monkeypatch.setattr(
        VERIFIER,
        "EXPECTED_GENERATION_CONFIG_SHA256",
        expected_hashes["generation_config.json"],
    )
    monkeypatch.setattr(
        VERIFIER,
        "EXPECTED_WEIGHT_SHA256",
        {"model.safetensors": expected_hashes["model.safetensors"]},
    )
    monkeypatch.setattr(
        VERIFIER,
        "EXPECTED_REMOTE_CODE_SHA256",
        {
            name: VERIFIER.sha256(snapshot / name)
            for name in VERIFIER.EXPECTED_REMOTE_CODE_SHA256
        },
    )
    assert VERIFIER.verify_snapshot(snapshot, None) == []
    (snapshot / "model.safetensors").write_bytes(b"tampered")
    assert "SNAPSHOT_HASH_MISMATCH:model.safetensors" in VERIFIER.verify_snapshot(
        snapshot, None
    )
