from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
        return torch.cat([torch.zeros_like(x_enc), torch.zeros_like(x_enc), forecast], dim=1)
""".strip()


def _script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "run_time_series_library_provider.py"


def _run(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_script()), "--request", str(request), "--response", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_scinet_rejects_tampered_checkpoint_geometry(tmp_path: Path) -> None:
    import torch

    source_root = tmp_path / "upstream"
    models = source_root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "SCINet.py").write_text(FAKE_SCINET, encoding="utf-8")

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
                "train_steps": 1,
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    checkpoint_path = Path(fit["artifacts"]["checkpoint"])
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    checkpoint["geometry"]["raw_output_length"] = 18
    torch.save(checkpoint, checkpoint_path)

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
    assert "checkpoint SCINet geometry mismatch" in payload["errors"][0]
