from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_time_series_library_provider.py"
CONTRACT_TEST = ROOT / "tests" / "time_series_library_campaign" / "test_film_contract.py"


def _load_string_fixture(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "strip"
            and isinstance(value.func.value, ast.Constant)
            and isinstance(value.func.value.value, str)
            and not value.args
            and not value.keywords
        ):
            return value.func.value.value.strip()
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        raise AssertionError(f"{name} is not a supported string fixture")
    raise AssertionError(f"{name} not found in {path}")


def write_fake_source(root: Path) -> None:
    source = _load_string_fixture(CONTRACT_TEST, "FAKE_FILM")
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "FiLM.py").write_text(source, encoding="utf-8")


def run_request(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--request", str(request), "--response", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_film_rejects_tampered_checkpoint_geometry(tmp_path: Path) -> None:
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
    checkpoint["geometry"]["spectral_modes"] += 1
    torch.save(checkpoint, checkpoint_path)
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
                "checkpoint_path": str(checkpoint_path),
                "input_path": fit["artifacts"]["input"],
            }
        ),
        encoding="utf-8",
    )
    second = run_request(load_request, load_response)
    assert second.returncode == 2
    payload = json.loads(load_response.read_text(encoding="utf-8"))
    assert "checkpoint FiLM geometry mismatch" in payload["errors"][0]
