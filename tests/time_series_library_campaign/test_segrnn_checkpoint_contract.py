from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _script() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run_time_series_library_provider.py"
    )


def _write_fake_source(root: Path) -> None:
    models = root / "models"
    layers = root / "layers"
    models.mkdir(parents=True)
    layers.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (layers / "__init__.py").write_text("", encoding="utf-8")
    (layers / "Autoformer_EncDec.py").write_text(
        "class series_decomp:\n    pass\n",
        encoding="utf-8",
    )
    (models / "SegRNN.py").write_text(
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
        + "\n",
        encoding="utf-8",
    )


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


def test_segrnn_rejects_tampered_checkpoint_geometry(tmp_path: Path) -> None:
    import torch

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
                "seq_len": 8,
                "pred_len": 4,
                "channels": 3,
                "train_steps": 1,
                "d_model": 16,
                "segrnn_seg_len": 2,
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    checkpoint_path = Path(fit["artifacts"]["checkpoint"])
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    checkpoint["geometry"]["seg_num_y"] = 999
    torch.save(checkpoint, checkpoint_path)

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
    assert "checkpoint SegRNN geometry mismatch" in payload["errors"][0]
