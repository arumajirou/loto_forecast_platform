from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from loto.time_series_library_campaign import ProviderRequest

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
        self.alpha = configs.alpha
        self.top_p = configs.top_p
        self.use_RevIN = False
        self.backbone = SimpleNamespace(n_blocks=configs.e_layers)
        self.linear = nn.Linear(configs.seq_len, configs.pred_len)

    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec, mask=None):
        return self.linear(x_enc.permute(0, 2, 1)).permute(0, 2, 1)
""".strip()


def _script() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "run_time_series_library_provider.py"


def _write_fake_source(root: Path) -> None:
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "TimeFilter.py").write_text(FAKE_TIMEFILTER, encoding="utf-8")


def _run(request: Path, response: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_script()), "--request", str(request), "--response", str(response)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_timefilter_operation_rejects_wrong_model_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_name=TimeFilter"):
        ProviderRequest(
            operation="timefilter_fit_save",
            model_name="SCINet",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
        )


def test_timefilter_rejects_nondivisible_patch_geometry(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="seq_len divisible by patch_len"):
        ProviderRequest(
            operation="timefilter_fit_save",
            model_name="TimeFilter",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=10,
            timefilter_patch_len=4,
        )


def test_timefilter_rejects_odd_d_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="even d_model"):
        ProviderRequest(
            operation="timefilter_fit_save",
            model_name="TimeFilter",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=8,
            d_model=9,
            timefilter_n_heads=3,
        )


def test_timefilter_rejects_nondivisible_heads(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="d_model divisible by n_heads"):
        ProviderRequest(
            operation="timefilter_fit_save",
            model_name="TimeFilter",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            seq_len=8,
            d_model=10,
            timefilter_n_heads=3,
        )


def test_timefilter_pinned_policy_rejects_fixture(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(
        json.dumps(
            {
                "operation": "timefilter_fit_save",
                "model_name": "TimeFilter",
                "source_root": str(source_root),
                "output_dir": str(tmp_path / "fit"),
                "seq_len": 8,
            }
        ),
        encoding="utf-8",
    )
    result = _run(request, response)
    assert result.returncode == 2
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "pinned source mismatch" in payload["errors"][0]


def test_timefilter_cross_process_roundtrip_fixture(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_source(source_root)
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
                "train_steps": 2,
            }
        ),
        encoding="utf-8",
    )
    first = _run(fit_request, fit_response)
    assert first.returncode == 0, first.stderr
    fit = json.loads(fit_response.read_text(encoding="utf-8"))
    assert fit["status"] == "PASS"
    assert fit["evidence"]["prediction_shape"] == [2, 3, 3]
    assert fit["evidence"]["graph_geometry"]["token_count"] == 12
    assert fit["evidence"]["source_identity"]["status"] == "TEST_FIXTURE"

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

    verify_request = tmp_path / "verify_request.json"
    verify_response = tmp_path / "verify_response.json"
    verify_request.write_text(
        json.dumps(
            {
                "operation": "verify_roundtrip",
                "model_name": "TimeFilter",
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
