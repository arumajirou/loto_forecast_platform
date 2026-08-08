from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loto.time_series_library_campaign import ProviderRequest


FAKE_FRETS = (
    """
import torch
from torch import nn

class Model(nn.Module):
    def __init__(self, configs):
        super().__init__()
        self.task_name = configs.task_name
        self.pred_len = configs.pred_len
        self.embed_size = 128
        self.hidden_size = 256
        self.feature_size = configs.enc_in
        self.seq_len = configs.seq_len
        self.channel_independence = configs.channel_independence
        self.sparsity_threshold = 0.01
        self.scale = 0.02
        self.embeddings = nn.Parameter(torch.randn(1, self.embed_size))
        self.r1 = nn.Parameter(self.scale * torch.randn(self.embed_size, self.embed_size))
        self.i1 = nn.Parameter(self.scale * torch.randn(self.embed_size, self.embed_size))
        self.rb1 = nn.Parameter(self.scale * torch.randn(self.embed_size))
        self.ib1 = nn.Parameter(self.scale * torch.randn(self.embed_size))
        self.r2 = nn.Parameter(self.scale * torch.randn(self.embed_size, self.embed_size))
        self.i2 = nn.Parameter(self.scale * torch.randn(self.embed_size, self.embed_size))
        self.rb2 = nn.Parameter(self.scale * torch.randn(self.embed_size))
        self.ib2 = nn.Parameter(self.scale * torch.randn(self.embed_size))
        self.fc = nn.Sequential(
            nn.Linear(self.seq_len * self.embed_size, self.hidden_size),
            nn.LeakyReLU(),
            nn.Linear(self.hidden_size, self.pred_len),
        )

    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec):
        batch, _, channels = x_enc.shape
        embedded = x_enc.permute(0, 2, 1).unsqueeze(-1) * self.embeddings
        return self.fc(embedded.reshape(batch, channels, -1)).permute(0, 2, 1)
""".strip()
    + "\n"
)


def _script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "run_time_series_library_provider.py"


def _write_fake_source(root: Path) -> None:
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "FreTS.py").write_text(FAKE_FRETS, encoding="utf-8")


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


def test_frets_operation_rejects_wrong_model_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_name=FreTS"):
        ProviderRequest(
            operation="frets_fit_save",
            model_name="SegRNN",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
        )


def test_frets_rejects_invalid_channel_independence(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProviderRequest(
            operation="frets_fit_save",
            model_name="FreTS",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            frets_channel_independence="2",
        )


def test_frets_pinned_policy_rejects_fixture(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "operation": "frets_fit_save",
                "model_name": "FreTS",
                "source_root": str(source_root),
                "output_dir": str(tmp_path / "fit"),
                "seq_len": 8,
                "pred_len": 2,
                "channels": 3,
            }
        ),
        encoding="utf-8",
    )
    result = _run(request, response)
    assert result.returncode == 2
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "pinned source mismatch" in payload["errors"][0]


@pytest.mark.parametrize("channel_independence", ["0", "1"])
def test_frets_cross_process_roundtrip_fixture(
    tmp_path: Path,
    channel_independence: str,
) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    fit_request = tmp_path / "fit_request.json"
    fit_response = tmp_path / "fit_response.json"
    fit_request.write_text(
        json.dumps(
            {
                "operation": "frets_fit_save",
                "model_name": "FreTS",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "fit"),
                "seed": 1,
                "seq_len": 8,
                "pred_len": 2,
                "channels": 3,
                "train_steps": 2,
                "frets_channel_independence": channel_independence,
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    assert fit["status"] == "PASS"
    geometry = fit["evidence"]["frequency_geometry"]
    assert geometry["channel_independence"] == channel_independence
    assert geometry["channel_frequency_mixing"] is (channel_independence == "0")
    assert geometry["temporal_fft_bins"] == 5
    assert geometry["channel_fft_bins"] == 2
    assert geometry["expected_parameter_count"] == 329090
    assert fit["evidence"]["source_identity"]["status"] == "TEST_FIXTURE"

    load_request = tmp_path / "load_request.json"
    load_response = tmp_path / "load_response.json"
    load_request.write_text(
        json.dumps(
            {
                "operation": "frets_load_predict",
                "model_name": "FreTS",
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
    assert load["evidence"]["frequency_geometry"] == geometry

    verify_request = tmp_path / "verify_request.json"
    verify_response = tmp_path / "verify_response.json"
    verify_request.write_text(
        json.dumps(
            {
                "operation": "verify_roundtrip",
                "model_name": "FreTS",
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
    ProviderRequest(
        operation="segrnn_fit_save",
        model_name="SegRNN",
        source_root=tmp_path,
        output_dir=tmp_path / "segrnn",
        seq_len=8,
        pred_len=4,
        d_model=16,
        segrnn_seg_len=2,
    )
