from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loto.time_series_library_campaign import ProviderRequest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_time_series_library_provider.py"

FAKE_TIDE = '''
import torch
from torch import nn

class LayerNorm(nn.Module):
    def __init__(self, ndim):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(ndim))
        self.bias = nn.Parameter(torch.zeros(ndim))
    def forward(self, x):
        return torch.nn.functional.layer_norm(x, self.weight.shape, self.weight, self.bias, 1e-5)

class ResBlock(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, output_dim)
        self.fc3 = nn.Linear(input_dim, output_dim)
        self.ln = LayerNorm(output_dim)
    def forward(self, x):
        return self.ln(self.fc2(torch.relu(self.fc1(x))) + self.fc3(x))

class Model(nn.Module):
    def __init__(self, configs):
        super().__init__()
        self.seq_len = configs.seq_len
        self.pred_len = configs.pred_len
        self.hidden_dim = configs.d_model
        self.encoder_num = configs.e_layers
        self.decoder_num = configs.d_layers
        self.freq = configs.freq
        self.feature_encode_dim = 2
        self.decode_dim = configs.c_out
        self.temporalDecoderHidden = configs.d_ff
        feature_dims = {'h': 4, 't': 5, 's': 6, 'm': 1, 'a': 1, 'w': 2, 'd': 3, 'b': 3}
        self.feature_dim = feature_dims[self.freq]
        flatten_dim = self.seq_len + (self.seq_len + self.pred_len) * 2
        self.feature_encoder = ResBlock(self.feature_dim, self.hidden_dim, 2)
        self.encoders = nn.Sequential(ResBlock(flatten_dim, self.hidden_dim, self.hidden_dim))
        self.decoders = nn.Sequential(
            ResBlock(self.hidden_dim, self.hidden_dim, self.decode_dim * self.pred_len)
        )
        self.temporalDecoder = ResBlock(self.decode_dim + 2, configs.d_ff, 1)
        self.residual_proj = nn.Linear(self.seq_len, self.pred_len)
    def forward(self, x_enc, x_mark_enc, x_dec, batch_y_mark, mask=None):
        values = [self.residual_proj(x_enc[:, :, index]) for index in range(x_enc.shape[-1])]
        return torch.stack(values, dim=-1)
'''.strip()


def write_fake_source(root: Path) -> None:
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "TiDE.py").write_text(FAKE_TIDE, encoding="utf-8")


def run_request(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--request", str(request), "--response", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_tide_rejects_wrong_model_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_name=TiDE"):
        ProviderRequest(
            operation="tide_fit_save",
            model_name="TimeFilter",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            e_layers=1,
            tide_d_layers=1,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("e_layers", 2, "e_layers=1"),
        ("tide_d_layers", 2, "e_layers=1"),
        ("dropout", 0.1, "dropout=0.0"),
    ],
)
def test_tide_rejects_unverified_depth_or_dropout(
    tmp_path: Path, field: str, value: int | float, message: str
) -> None:
    payload = {
        "operation": "tide_fit_save",
        "model_name": "TiDE",
        "source_root": tmp_path,
        "output_dir": tmp_path / "out",
        "e_layers": 1,
        "tide_d_layers": 1,
        "dropout": 0.0,
    }
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        ProviderRequest(**payload)


def test_tide_pinned_policy_rejects_fixture(tmp_path: Path) -> None:
    source = tmp_path / "source"
    write_fake_source(source)
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "operation": "tide_fit_save",
                "model_name": "TiDE",
                "source_root": str(source),
                "output_dir": str(tmp_path / "out"),
                "e_layers": 1,
                "tide_d_layers": 1,
            }
        ),
        encoding="utf-8",
    )
    result = run_request(request, response)
    assert result.returncode == 2
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "pinned source mismatch" in payload["errors"][0]


def test_tide_cross_process_roundtrip_fixture(tmp_path: Path) -> None:
    source = tmp_path / "source"
    write_fake_source(source)
    fit_request = tmp_path / "fit_request.json"
    fit_response = tmp_path / "fit_response.json"
    fit_request.write_text(
        json.dumps(
            {
                "operation": "tide_fit_save",
                "model_name": "TiDE",
                "source_root": str(source),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "fit"),
                "seq_len": 8,
                "pred_len": 2,
                "channels": 3,
                "d_model": 8,
                "e_layers": 1,
                "tide_d_layers": 1,
                "tide_d_ff": 16,
                "tide_freq": "h",
                "dropout": 0.0,
                "train_steps": 2,
            }
        ),
        encoding="utf-8",
    )
    first = run_request(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    load_request = tmp_path / "load_request.json"
    load_response = tmp_path / "load_response.json"
    load_request.write_text(
        json.dumps(
            {
                "operation": "tide_load_predict",
                "model_name": "TiDE",
                "source_root": str(source),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "load"),
                "checkpoint_path": fit["artifacts"]["checkpoint"],
                "input_path": fit["artifacts"]["input"],
            }
        ),
        encoding="utf-8",
    )
    second = run_request(load_request, load_response)
    assert second.returncode == 0, second.stderr
    load = json.loads(load_response.read_text(encoding="utf-8"))
    assert fit["evidence"]["process_id"] != load["evidence"]["process_id"]
    assert load["evidence"]["strict_state_load"] is True
    assert fit["evidence"]["prediction_sha256"] == load["evidence"]["prediction_sha256"]
