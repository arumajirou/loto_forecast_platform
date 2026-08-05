from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from loto.adapters.toto2_4m.contracts import Toto2ProviderRequest
from loto.toto2_campaign.runtime_executor import (
    SnapshotIntegrityError,
    history_to_numpy,
    verify_snapshot,
)


def _payload(*, context_length: int = 128, decode_block_size: int = 32) -> dict[str, object]:
    columns = ["p1", "p2", "p3"]
    history = [
        {name: float(row + index) for index, name in enumerate(columns)}
        for row in range(context_length + 2)
    ]
    return {
        "schema_version": 2,
        "run_id": "runtime-test",
        "operation": "predict",
        "model_id": "toto-2.0-4m",
        "repo_id": "Datadog/Toto-2.0-4m",
        "revision": "8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9",
        "source_revision": "44ea4e88852228039564aa3e76fac26aafac0803",
        "model_license": "Apache-2.0",
        "game_geometry": {
            "game_id": "numbers3",
            "position_count": 3,
            "candidate_min": 0,
            "candidate_max": 9,
            "strictly_increasing": False,
        },
        "series_layout": "position_multivariate",
        "position_columns": columns,
        "history": history,
        "timestamps": list(range(100, 100 + len(history))),
        "time_semantics": "draw_sequence",
        "context_length": context_length,
        "prediction_length": 1,
        "native_quantile_levels": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "point_method": "median_q0.5",
        "batch_size": 1,
        "decode_block_size": decode_block_size,
        "device": "cpu",
        "dtype": "float32",
        "seed": 1,
        "local_files_only": True,
        "snapshot_path": None,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_history_to_numpy_uses_only_trailing_context() -> None:
    request = Toto2ProviderRequest.model_validate(_payload(context_length=128))
    target = history_to_numpy(request)
    assert target.shape == (1, 3, 128)
    assert target.dtype == np.float32
    assert target[0, 0, :3].tolist() == [2.0, 3.0, 4.0]
    assert target[0, 2, -3:].tolist() == [129.0, 130.0, 131.0]


def test_snapshot_verification_accepts_exact_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = tmp_path / "revision-test"
    snapshot.mkdir()
    (snapshot / "README.md").write_text("readme\n", encoding="utf-8")
    (snapshot / "config.json").write_text(json.dumps({"patch_size": 32}), encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"weights")
    names = ["README.md", "config.json", "model.safetensors"]
    expected = {name: _sha(snapshot / name) for name in names}
    monkeypatch.setattr("loto.toto2_campaign.runtime_executor.MODEL_REVISION", "revision-test")
    monkeypatch.setattr("loto.toto2_campaign.runtime_executor.ARTIFACT_SHA256", expected)
    monkeypatch.setattr(
        "loto.toto2_campaign.runtime_executor.ARTIFACT_SIZE_BYTES",
        {"model.safetensors": 7},
    )
    evidence = verify_snapshot(snapshot)
    assert evidence["revision"] == "revision-test"
    assert evidence["files"]["model.safetensors"]["size_bytes"] == 7


def test_snapshot_verification_rejects_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = tmp_path / "revision-test"
    snapshot.mkdir()
    (snapshot / "README.md").write_text("readme\n", encoding="utf-8")
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"weights")
    names = ["README.md", "config.json", "model.safetensors"]
    expected = {name: _sha(snapshot / name) for name in names}
    expected["model.safetensors"] = "0" * 64
    monkeypatch.setattr("loto.toto2_campaign.runtime_executor.MODEL_REVISION", "revision-test")
    monkeypatch.setattr("loto.toto2_campaign.runtime_executor.ARTIFACT_SHA256", expected)
    monkeypatch.setattr(
        "loto.toto2_campaign.runtime_executor.ARTIFACT_SIZE_BYTES",
        {"model.safetensors": 7},
    )
    with pytest.raises(SnapshotIntegrityError, match="SHA-256 mismatch"):
        verify_snapshot(snapshot)


def test_prepare_and_forecast_with_injected_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import torch

    from loto.toto2_campaign.runtime_executor import forecast_prepared, prepare_runtime

    class OutputHead:
        knots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

    class Config:
        patch_size = 32

    class Toto2Model(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.weight = torch.nn.Parameter(torch.zeros(4_144_448))
            self.config = Config()
            self.output_head = OutputHead()

        @classmethod
        def from_pretrained(cls, path: str) -> "Toto2Model":
            assert path
            return cls()

        def forecast(
            self,
            inputs: dict[str, torch.Tensor],
            *,
            horizon: int,
            decode_block_size: int,
            has_missing_values: bool,
        ) -> torch.Tensor:
            assert decode_block_size == 32
            assert has_missing_values is False
            target = inputs["target"]
            quantiles = torch.arange(1, 10, device=target.device, dtype=torch.float32)
            return quantiles[:, None, None, None].expand(
                9, target.shape[0], target.shape[1], horizon
            )

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setattr(
        "loto.toto2_campaign.runtime_executor.verify_snapshot",
        lambda path: {"snapshot_path": str(snapshot), "revision": "test", "files": {}},
    )

    def dependency_loader():
        return (
            torch,
            Toto2Model,
            {
                "python_version": "3.12.13",
                "torch_version": "2.13.0+cpu",
                "torch_cuda_version": None,
                "toto_2_version": "2.0.0",
                "toto_models_version": "1.0.0",
            },
        )

    request = Toto2ProviderRequest.model_validate(_payload(context_length=128))
    prepared = prepare_runtime(
        request,
        snapshot,
        dependency_loader=dependency_loader,
    )
    native_output, evidence, artifact = forecast_prepared(request, prepared)
    assert native_output.shape == (9, 1, 3, 1)
    assert evidence.runtime_scope == "FULL_INFERENCE"
    assert evidence.cpu_fallback is False
    assert artifact["output_finite"] is True
    assert artifact["quantile_monotonicity"] is True
