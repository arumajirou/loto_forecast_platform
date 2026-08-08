from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loto.time_series_library_campaign import ProviderRequest

FAKE_SCINET = """
import torch
from torch import nn

class Model(nn.Module):
    def __init__(self, configs):
        super().__init__()
        self.seq_len = configs.seq_len
        self.pred_len = configs.pred_len
        self.num_stacks = configs.d_layers
        self.pe_hidden_size = configs.enc_in if configs.enc_in % 2 == 0 else configs.enc_in + 1
        self.register_buffer("inv_timescales", torch.ones(self.pe_hidden_size // 2))
        self.linear = nn.Linear(configs.seq_len, configs.pred_len)

    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec, mask=None):
        forecast = self.linear(x_enc.permute(0, 2, 1)).permute(0, 2, 1)
        middle = torch.zeros_like(x_enc)
        return torch.cat([torch.zeros_like(x_enc), middle, forecast], dim=1)
""".strip()


def _script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "run_time_series_library_provider.py"


def _write_fake_source(root: Path) -> None:
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "SCINet.py").write_text(FAKE_SCINET, encoding="utf-8")


def _run(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_script()), "--request", str(request), "--response", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_scinet_operation_rejects_wrong_model_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_name=SCINet"):
        ProviderRequest(
            operation="scinet_fit_save",
            model_name="FreTS",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=8,
        )


def test_scinet_rejects_short_sequence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="seq_len >= 8"):
        ProviderRequest(
            operation="scinet_fit_save",
            model_name="SCINet",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=7,
        )


def test_scinet_rejects_nonzero_dropout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dropout=0.0"):
        ProviderRequest(
            operation="scinet_fit_save",
            model_name="SCINet",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=8,
            dropout=0.1,
        )


def test_scinet_rejects_invalid_stack_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProviderRequest(
            operation="scinet_fit_save",
            model_name="SCINet",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=8,
            scinet_stacks=3,
        )


def test_scinet_pinned_policy_rejects_fixture(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "operation": "scinet_fit_save",
                "model_name": "SCINet",
                "source_root": str(source_root),
                "output_dir": str(tmp_path / "fit"),
                "seq_len": 8,
            }
        ),
        encoding="utf-8",
    )
    result = _run(request, response)
    assert result.returncode == 2
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "pinned source mismatch" in payload["errors"][0]


def test_scinet_cross_process_roundtrip_fixture(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    fit_request = tmp_path / "fit_request.json"
    fit_response = tmp_path / "fit_response.json"
    fit_request.write_text(
        json.dumps(
            {
                "operation": "scinet_fit_save",
                "model_name": "SCINet",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "fit"),
                "seq_len": 8,
                "pred_len": 3,
                "channels": 3,
                "scinet_stacks": 1,
                "train_steps": 2,
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    assert fit["status"] == "PASS"
    assert fit["evidence"]["raw_output_shape"] == [2, 19, 3]
    assert fit["evidence"]["prediction_shape"] == [2, 3, 3]
    assert fit["evidence"]["zero_prefix_verified"] is True
    assert fit["evidence"]["source_identity"]["status"] == "TEST_FIXTURE"

    load_request = tmp_path / "load_request.json"
    load_response = tmp_path / "load_response.json"
    load_request.write_text(
        json.dumps(
            {
                "operation": "scinet_load_predict",
                "model_name": "SCINet",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "load"),
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

    verify_request = tmp_path / "verify_request.json"
    verify_response = tmp_path / "verify_response.json"
    verify_request.write_text(
        json.dumps(
            {
                "operation": "verify_roundtrip",
                "model_name": "SCINet",
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
