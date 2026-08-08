from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FAKE_TIMEFILTER = """
import torch
from torch import nn
from types import SimpleNamespace

class Model(nn.Module):
    def __init__(self, configs):
        super().__init__()
        self.seq_len = configs.seq_len
        self.pred_len = configs.pred_len
        self.n_vars = configs.c_out
        self.dim = configs.d_model
        self.d_ff = configs.d_ff
        self.patch_len = configs.patch_len
        self.stride = configs.patch_len
        self.num_patches = configs.seq_len // configs.patch_len
        self.backbone = SimpleNamespace(n_blocks=configs.e_layers)
        self.linear = nn.Linear(configs.seq_len, configs.pred_len)

    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec, mask=None):
        return self.linear(x_enc.permute(0, 2, 1)).permute(0, 2, 1)
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


def test_timefilter_rejects_tampered_checkpoint_geometry(tmp_path: Path) -> None:
    import torch

    source_root = tmp_path / "upstream"
    models = source_root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "TimeFilter.py").write_text(FAKE_TIMEFILTER, encoding="utf-8")
    fit_request = tmp_path / "fit_request.json"
    fit_response = tmp_path / "fit_response.json"
    fit_request.write_text(
        json.dumps(
            {
                "operation": "timefilter_fit_save",
                "model_name": "TimeFilter",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(tmp_path / "fit"),
                "seq_len": 8,
                "pred_len": 3,
                "channels": 3,
                "d_model": 8,
                "timefilter_patch_len": 2,
                "timefilter_n_heads": 2,
                "timefilter_d_ff": 16,
                "e_layers": 1,
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
    checkpoint["geometry"]["token_count"] = 11
    torch.save(checkpoint, checkpoint_path)

    load_request = tmp_path / "load_request.json"
    load_response = tmp_path / "load_response.json"
    load_request.write_text(
        json.dumps(
            {
                "operation": "timefilter_load_predict",
                "model_name": "TimeFilter",
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
    assert "checkpoint TimeFilter geometry mismatch" in payload["errors"][0]
