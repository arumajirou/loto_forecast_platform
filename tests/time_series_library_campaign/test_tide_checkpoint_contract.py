from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_time_series_library_provider.py"

FAKE_TIDE = (ROOT / "tests" / "time_series_library_campaign" / "test_tide_contract.py")

def write_fake_source(root: Path) -> None:
    source = FAKE_TIDE.read_text(encoding="utf-8")
    marker = "FAKE_TIDE = '''\n"
    start = source.index(marker) + len(marker)
    end = source.index("\n'''.strip()", start)
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "TiDE.py").write_text(source[start:end], encoding="utf-8")

def run_request(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--request", str(request), "--response", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_tide_rejects_tampered_checkpoint_geometry(tmp_path: Path) -> None:
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
                "train_steps": 1,
            }
        ),
        encoding="utf-8",
    )
    first = run_request(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    checkpoint_path = Path(fit["artifacts"]["checkpoint"])
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    checkpoint["geometry"]["flatten_dim"] += 1
    torch.save(checkpoint, checkpoint_path)
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
                "checkpoint_path": str(checkpoint_path),
                "input_path": fit["artifacts"]["input"],
            }
        ),
        encoding="utf-8",
    )
    second = run_request(load_request, load_response)
    assert second.returncode == 2
    payload = json.loads(load_response.read_text(encoding="utf-8"))
    assert "checkpoint TiDE geometry mismatch" in payload["errors"][0]
