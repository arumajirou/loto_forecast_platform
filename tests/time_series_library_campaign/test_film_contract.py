from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loto.time_series_library_campaign import ProviderRequest
from loto.time_series_library_campaign.film_runtime import ensure_cpu_only_runtime

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_time_series_library_provider.py"

FAKE_FILM = '''
import torch
from torch import nn

device = torch.device("cpu")

class FakeLegT(nn.Module):
    def __init__(self, pred_len, scale):
        super().__init__()
        self.N = 256
        self.register_buffer("A", torch.eye(256))
        self.register_buffer("B", torch.ones(256))
        self.register_buffer("eval_matrix", torch.ones(pred_len * scale, 256))

class FakeSpectral(nn.Module):
    def __init__(self, modes):
        super().__init__()
        self.modes = modes
        self.weights_real = nn.Parameter(torch.zeros(256, 256, modes))
        self.weights_imag = nn.Parameter(torch.zeros(256, 256, modes))

class Model(nn.Module):
    def __init__(self, configs):
        super().__init__()
        self.task_name = configs.task_name
        self.seq_len = configs.seq_len
        self.label_len = configs.label_len
        self.pred_len = configs.pred_len
        self.layers = configs.e_layers
        self.enc_in = configs.enc_in
        self.e_layers = configs.e_layers
        self.multiscale = [1, 2, 4]
        self.window_size = [256]
        self.affine_weight = nn.Parameter(torch.ones(1, 1, configs.enc_in))
        self.affine_bias = nn.Parameter(torch.zeros(1, 1, configs.enc_in))
        modes = min(32, min(configs.pred_len, configs.seq_len) // 2)
        self.legts = nn.ModuleList([FakeLegT(configs.pred_len, scale) for scale in self.multiscale])
        self.spec_conv_1 = nn.ModuleList([FakeSpectral(modes) for _ in self.multiscale])
        self.mlp = nn.Linear(3, 1)
    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec, mask=None):
        base = x_enc[:, -1:, :] * self.affine_weight + self.affine_bias
        stacked = torch.stack([base, base, base], dim=-1)
        mixed = self.mlp(stacked).squeeze(-1)
        return mixed.repeat(1, self.pred_len, 1)
'''.strip()


def write_fake_source(root: Path) -> None:
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "FiLM.py").write_text(FAKE_FILM, encoding="utf-8")


def run_request(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--request", str(request), "--response", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_film_rejects_wrong_model_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_name=FiLM"):
        ProviderRequest(
            operation="film_fit_save",
            model_name="TiDE",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            pred_len=2,
            seq_len=8,
            e_layers=1,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pred_len", 1, "pred_len >= 2"),
        ("seq_len", 7, "seq_len >= 4 \\* pred_len"),
        ("e_layers", 2, "e_layers=1"),
        ("dropout", 0.1, "dropout=0.0"),
    ],
)
def test_film_rejects_unverified_geometry(
    tmp_path: Path, field: str, value: int | float, message: str
) -> None:
    payload = {
        "operation": "film_fit_save",
        "model_name": "FiLM",
        "source_root": tmp_path,
        "output_dir": tmp_path / "out",
        "seq_len": 8,
        "pred_len": 2,
        "e_layers": 1,
        "dropout": 0.0,
    }
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        ProviderRequest(**payload)



def test_film_rejects_cuda_visible_cpu_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    with pytest.raises(ValueError, match="requires CUDA unavailable"):
        ensure_cpu_only_runtime()

def test_film_pinned_policy_rejects_fixture(tmp_path: Path) -> None:
    source = tmp_path / "source"
    write_fake_source(source)
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "operation": "film_fit_save",
                "model_name": "FiLM",
                "source_root": str(source),
                "output_dir": str(tmp_path / "out"),
                "seq_len": 8,
                "pred_len": 2,
                "e_layers": 1,
            }
        ),
        encoding="utf-8",
    )
    result = run_request(request, response)
    assert result.returncode == 2
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "pinned source mismatch" in payload["errors"][0]


def test_film_cross_process_roundtrip_fixture(tmp_path: Path) -> None:
    source = tmp_path / "source"
    write_fake_source(source)
    fit_request = tmp_path / "fit_request.json"
    fit_response = tmp_path / "fit_response.json"
    fit_request.write_text(
        json.dumps(
            {
                "operation": "film_fit_save",
                "model_name": "FiLM",
                "source_root": str(source),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "fit"),
                "seq_len": 8,
                "pred_len": 2,
                "channels": 3,
                "e_layers": 1,
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
                "operation": "film_load_predict",
                "model_name": "FiLM",
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
