from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loto.time_series_library_campaign import ProviderRequest

FAKE_SEGRNN = (
    """
import torch
from torch import nn
from layers.Autoformer_EncDec import series_decomp

class Model(nn.Module):
    def __init__(self, configs):
        super().__init__()
        self.seq_len = configs.seq_len
        self.pred_len = configs.pred_len
        self.enc_in = configs.enc_in
        self.d_model = configs.d_model
        self.seg_len = configs.seg_len
        self.seg_num_x = self.seq_len // self.seg_len
        self.seg_num_y = self.pred_len // self.seg_len
        self.pos_emb = nn.Parameter(torch.randn(self.seg_num_y, self.d_model // 2))
        self.channel_emb = nn.Parameter(torch.randn(self.enc_in, self.d_model // 2))
        self.linear = nn.Linear(self.seq_len, self.pred_len)

    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec, mask=None):
        return self.linear(x_enc.permute(0, 2, 1)).permute(0, 2, 1)
""".strip()
    + "\n"
)

FAKE_AUTOFORMER = (
    """
class series_decomp:
    pass
""".strip()
    + "\n"
)


def _script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "run_time_series_library_provider.py"


def _write_fake_source(root: Path) -> None:
    models = root / "models"
    layers = root / "layers"
    models.mkdir(parents=True)
    layers.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (layers / "__init__.py").write_text("", encoding="utf-8")
    (models / "SegRNN.py").write_text(FAKE_SEGRNN, encoding="utf-8")
    (layers / "Autoformer_EncDec.py").write_text(FAKE_AUTOFORMER, encoding="utf-8")


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


def test_segrnn_operation_rejects_wrong_model_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_name=SegRNN"):
        ProviderRequest(
            operation="segrnn_fit_save",
            model_name="LightTS",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            pred_len=4,
        )


def test_segrnn_rejects_odd_d_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="even d_model"):
        ProviderRequest(
            operation="segrnn_fit_save",
            model_name="SegRNN",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            pred_len=4,
            d_model=15,
        )


def test_segrnn_rejects_non_divisible_sequence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="seq_len divisible"):
        ProviderRequest(
            operation="segrnn_fit_save",
            model_name="SegRNN",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=9,
            pred_len=4,
            segrnn_seg_len=2,
        )


def test_segrnn_rejects_non_divisible_horizon(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pred_len divisible"):
        ProviderRequest(
            operation="segrnn_fit_save",
            model_name="SegRNN",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=8,
            pred_len=5,
            segrnn_seg_len=2,
        )


def test_segrnn_pinned_policy_rejects_fixture(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "operation": "segrnn_fit_save",
                "model_name": "SegRNN",
                "source_root": str(source_root),
                "output_dir": str(tmp_path / "fit"),
                "seq_len": 8,
                "pred_len": 4,
                "segrnn_seg_len": 2,
            }
        ),
        encoding="utf-8",
    )
    result = _run(request, response)
    assert result.returncode == 2
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "pinned source mismatch" in payload["errors"][0]


def test_segrnn_cross_process_roundtrip_fixture(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    fit_request = tmp_path / "fit_request.json"
    fit_response = tmp_path / "fit_response.json"
    fit_request.write_text(
        json.dumps(
            {
                "operation": "segrnn_fit_save",
                "model_name": "SegRNN",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "fit"),
                "seed": 1,
                "seq_len": 8,
                "pred_len": 4,
                "channels": 3,
                "train_steps": 2,
                "d_model": 16,
                "dropout": 0.0,
                "segrnn_seg_len": 2,
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    assert fit["status"] == "PASS"
    geometry = fit["evidence"]["segment_geometry"]
    assert geometry["seg_num_x"] == 4
    assert geometry["seg_num_y"] == 2
    assert geometry["half_width"] == 8
    assert fit["evidence"]["source_identity"]["status"] == "TEST_FIXTURE"

    load_request = tmp_path / "load_request.json"
    load_response = tmp_path / "load_response.json"
    load_request.write_text(
        json.dumps(
            {
                "operation": "segrnn_load_predict",
                "model_name": "SegRNN",
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
    assert load["evidence"]["segment_geometry"] == geometry

    verify_request = tmp_path / "verify_request.json"
    verify_response = tmp_path / "verify_response.json"
    verify_request.write_text(
        json.dumps(
            {
                "operation": "verify_roundtrip",
                "model_name": "SegRNN",
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


def test_existing_model_requests_remain_valid(tmp_path: Path) -> None:
    ProviderRequest(
        operation="dlinear_fit_save",
        model_name="DLinear",
        source_root=tmp_path,
        output_dir=tmp_path / "dlinear",
    )
    ProviderRequest(
        operation="tsmixer_fit_save",
        model_name="TSMixer",
        source_root=tmp_path,
        output_dir=tmp_path / "tsmixer",
    )
    ProviderRequest(
        operation="lightts_fit_save",
        model_name="LightTS",
        source_root=tmp_path,
        output_dir=tmp_path / "lightts",
        seq_len=8,
        pred_len=4,
        d_model=16,
    )
