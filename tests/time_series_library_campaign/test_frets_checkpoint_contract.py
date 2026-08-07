from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


FAKE_FRETS = """
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


def test_frets_rejects_tampered_checkpoint_geometry(tmp_path: Path) -> None:
    import torch

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
                "seq_len": 8,
                "pred_len": 2,
                "channels": 3,
                "train_steps": 1,
                "frets_channel_independence": "0",
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    checkpoint_path = Path(fit["artifacts"]["checkpoint"])
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    checkpoint["geometry"]["temporal_fft_bins"] = 999
    torch.save(checkpoint, checkpoint_path)

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
                "checkpoint_path": str(checkpoint_path),
                "input_path": fit["artifacts"]["input"],
            }
        ),
        encoding="utf-8",
    )
    second = _run(load_request, load_response)
    assert second.returncode == 2
    payload = json.loads(load_response.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "checkpoint FreTS geometry mismatch" in payload["errors"][0]
