from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FAKE_LIGHTTS = (
    """
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
                [x_enc, torch.zeros(x_enc.shape[0], pad, x_enc.shape[2])],
                dim=1,
            )
        return self.linear(x_enc.permute(0, 2, 1)).permute(0, 2, 1)
""".strip()
    + "\n"
)


def _script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts/run_time_series_library_provider.py"


def _write_fake_source(root: Path) -> None:
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "LightTS.py").write_text(FAKE_LIGHTTS, encoding="utf-8")


def _run(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_script()), "--request", str(request), "--response", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_lightts_rejects_tampered_checkpoint_geometry(tmp_path: Path) -> None:
    import torch

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
                "seq_len": 8,
                "pred_len": 5,
                "channels": 3,
                "train_steps": 1,
                "d_model": 16,
                "lightts_allow_padding": True,
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    checkpoint_path = Path(fit["artifacts"]["checkpoint"])
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    checkpoint["geometry"]["padding_length"] = 0
    torch.save(checkpoint, checkpoint_path)

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
                "d_model": 16,
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
    assert "checkpoint LightTS geometry mismatch" in payload["errors"][0]
