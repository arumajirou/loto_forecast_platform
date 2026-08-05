from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loto.time_series_library_campaign import ProviderRequest


FAKE_LIGHTTS = """
import torch
from torch import nn

class Model(nn.Module):
    def __init__(self, configs, chunk_size=24):
        super().__init__()
        self.pred_len = configs.pred_len
        self.chunk_size = min(configs.pred_len, configs.seq_len, chunk_size)
        self.seq_len = configs.seq_len
        if self.seq_len % self.chunk_size != 0:
            self.seq_len += self.chunk_size - self.seq_len % self.chunk_size
        self.num_chunks = self.seq_len // self.chunk_size
        self.linear = nn.Linear(self.seq_len, configs.pred_len)

    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec, mask=None):
        pad = self.seq_len - x_enc.shape[1]
        if pad:
            x_enc = torch.cat(
                [
                    x_enc,
                    torch.zeros(
                        x_enc.shape[0],
                        pad,
                        x_enc.shape[2],
                        device=x_enc.device,
                        dtype=x_enc.dtype,
                    ),
                ],
                dim=1,
            )
        x = x_enc.permute(0, 2, 1)
        return self.linear(x).permute(0, 2, 1)
""".strip() + "\n"


def _script() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run_time_series_library_provider.py"
    )


def _write_fake_source(root: Path) -> None:
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "LightTS.py").write_text(FAKE_LIGHTTS, encoding="utf-8")


def _run(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(_script()),
            "--request",
            str(request),
            "--response",
            str(response),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_lightts_operation_rejects_wrong_model_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProviderRequest(
            operation="lightts_fit_save",
            model_name="TSMixer",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
        )


def test_lightts_rejects_too_small_d_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="d_model >= 16"):
        ProviderRequest(
            operation="lightts_fit_save",
            model_name="LightTS",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            d_model=12,
        )


def test_lightts_rejects_non_divisible_d_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="divisible by 4"):
        ProviderRequest(
            operation="lightts_fit_save",
            model_name="LightTS",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            d_model=18,
        )


def test_lightts_rejects_implicit_padding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="lightts_allow_padding=true"):
        ProviderRequest(
            operation="lightts_fit_save",
            model_name="LightTS",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=8,
            pred_len=5,
            d_model=16,
        )


def test_lightts_pinned_policy_rejects_fixture(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "operation": "lightts_fit_save",
                "model_name": "LightTS",
                "source_root": str(source_root),
                "output_dir": str(tmp_path / "fit"),
                "d_model": 16,
            }
        ),
        encoding="utf-8",
    )
    result = _run(request, response)
    assert result.returncode == 2
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "pinned source mismatch" in payload["errors"][0]


def test_lightts_cross_process_roundtrip_fixture_with_padding(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    fit_request = tmp_path / "fit_request.json"
    fit_response = tmp_path / "fit_response.json"
    fit_request.write_text(
        json.dumps(
            {
                "operation": "lightts_fit_save",
                "model_name": "LightTS",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "fit"),
                "seed": 1,
                "seq_len": 8,
                "pred_len": 5,
                "channels": 3,
                "train_steps": 2,
                "d_model": 16,
                "dropout": 0.0,
                "lightts_chunk_size": 24,
                "lightts_allow_padding": True,
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    assert fit["status"] == "PASS"
    geometry = fit["evidence"]["chunk_geometry"]
    assert geometry["requested_chunk_size"] == 24
    assert geometry["chunk_size"] == 5
    assert geometry["allow_padding"] is True
    assert geometry["padded_seq_len"] == 10
    assert geometry["padding_length"] == 2
    assert geometry["num_chunks"] == 2
    assert fit["evidence"]["source_identity"]["status"] == "TEST_FIXTURE"

    load_request = tmp_path / "load_request.json"
    load_response = tmp_path / "load_response.json"
    load_request.write_text(
        json.dumps(
            {
                "operation": "lightts_load_predict",
                "model_name": "LightTS",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "load"),
                "seed": 1,
                "d_model": 16,
                "checkpoint_path": fit["artifacts"]["checkpoint"],
                "input_path": fit["artifacts"]["input"],
            }
        ),
        encoding="utf-8",
    )
    second = _run(load_request, load_response)
    assert second.returncode == 0, second.stderr
    load = json.loads(load_response.read_text(encoding="utf-8"))
    assert load["status"] == "PASS"
    assert load["evidence"]["strict_state_load"] is True
    assert load["evidence"]["chunk_geometry"] == geometry

    verify_request = tmp_path / "verify_request.json"
    verify_response = tmp_path / "verify_response.json"
    verify_request.write_text(
        json.dumps(
            {
                "operation": "verify_roundtrip",
                "model_name": "LightTS",
                "source_root": str(source_root),
                "output_dir": str(tmp_path / "verify"),
                "before_prediction_path": fit["artifacts"]["prediction_before"],
                "after_prediction_path": load["artifacts"]["prediction_after"],
            }
        ),
        encoding="utf-8",
    )
    third = _run(verify_request, verify_response)
    assert third.returncode == 0, third.stderr
    verification = json.loads(verify_response.read_text(encoding="utf-8"))
    assert verification["status"] == "PASS"
    assert verification["evidence"]["max_abs_error"] == 0.0
