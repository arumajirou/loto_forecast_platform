from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.time_series_library_campaign import (
    GameGeometry,
    ProviderRequest,
    SplitContract,
    discover_models,
    materialize_training_bundle,
)


def _write_fake_tslib(root: Path) -> None:
    models = root / "models"
    models.mkdir(parents=True)
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "Ignored.py").write_text("class Other:\n    pass\n", encoding="utf-8")
    (models / "DLinear.py").write_text(
        """
import torch
from torch import nn

class Model(nn.Module):
    def __init__(self, configs):
        super().__init__()
        self.pred_len = configs.pred_len
        self.linear = nn.Linear(configs.seq_len, configs.pred_len)

    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec, mask=None):
        x = x_enc.permute(0, 2, 1)
        return self.linear(x).permute(0, 2, 1)
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _frame(rows: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": np.arange(1, rows + 1),
            "draw_date": pd.date_range("2026-01-01", periods=rows, freq="7D"),
            "n1": (np.arange(rows) % 9) + 1,
            "n2": (np.arange(rows) % 9) + 1,
            "n3": (np.arange(rows) % 9) + 1,
        }
    )


def _script() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run_time_series_library_provider.py"
    )


def test_split_contract_fails_closed() -> None:
    with pytest.raises(ValueError):
        SplitContract(
            train_end_exclusive=8,
            validation_end_exclusive=7,
            holdout_end_exclusive=10,
        )


def test_discovery_uses_source_inventory_without_importing(tmp_path: Path) -> None:
    _write_fake_tslib(tmp_path)
    inventory = discover_models(tmp_path)
    assert [row["model_name"] for row in inventory] == ["DLinear"]
    assert inventory[0]["runtime_status"] == "EXECUTION_PENDING"


def test_training_bundle_excludes_holdout_and_prospective(tmp_path: Path) -> None:
    geometry = GameGeometry(
        game_id="numbers3",
        position_columns=("n1", "n2", "n3"),
        candidate_min=0,
        candidate_max=9,
    )
    split = SplitContract(
        train_end_exclusive=6,
        validation_end_exclusive=8,
        holdout_end_exclusive=10,
    )
    manifest = materialize_training_bundle(_frame(), geometry, split, tmp_path)
    assert manifest["excluded_by_contract"] == ["holdout", "prospective"]
    assert len(pd.read_csv(tmp_path / "train.csv")) == 6
    assert len(pd.read_csv(tmp_path / "validation.csv")) == 2
    assert not (tmp_path / "holdout.csv").exists()
    assert not (tmp_path / "prospective.csv").exists()


def test_provider_request_rejects_gpu_in_core_lane(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProviderRequest(
            operation="discover",
            source_root=tmp_path,
            output_dir=tmp_path / "out",
            device="cuda",
        )


def test_pinned_policy_rejects_unverified_source(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_tslib(source_root)
    request_path = tmp_path / "request.json"
    response_path = tmp_path / "response.json"
    request_path.write_text(
        json.dumps(
            {
                "operation": "dlinear_fit_save",
                "source_root": str(source_root),
                "output_dir": str(tmp_path / "fit"),
                "train_steps": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(_script()),
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    assert payload["status"] == "FAILED"
    assert "pinned source" in payload["errors"][0]


def test_dlinear_cross_process_save_load_roundtrip(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    _write_fake_tslib(source_root)
    script = _script()
    fit_dir = tmp_path / "fit"
    fit_request = tmp_path / "fit_request.json"
    fit_response = tmp_path / "fit_response.json"
    fit_request.write_text(
        json.dumps(
            {
                "operation": "dlinear_fit_save",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(fit_dir),
                "seed": 1,
                "seq_len": 8,
                "pred_len": 2,
                "channels": 3,
                "train_steps": 2,
            }
        ),
        encoding="utf-8",
    )
    first = subprocess.run(
        [
            sys.executable,
            str(script),
            "--request",
            str(fit_request),
            "--response",
            str(fit_response),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    fit_payload = json.loads(fit_response.read_text(encoding="utf-8"))
    assert fit_payload["status"] == "PASS"
    assert fit_payload["evidence"]["source_identity"]["status"] == "TEST_FIXTURE"

    load_dir = tmp_path / "load"
    load_request = tmp_path / "load_request.json"
    load_response = tmp_path / "load_response.json"
    load_request.write_text(
        json.dumps(
            {
                "operation": "dlinear_load_predict",
                "source_root": str(source_root),
                "source_policy": "test_fixture",
                "output_dir": str(load_dir),
                "seed": 1,
                "checkpoint_path": fit_payload["artifacts"]["checkpoint"],
                "input_path": fit_payload["artifacts"]["input"],
            }
        ),
        encoding="utf-8",
    )
    second = subprocess.run(
        [
            sys.executable,
            str(script),
            "--request",
            str(load_request),
            "--response",
            str(load_response),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert second.returncode == 0, second.stderr
    load_payload = json.loads(load_response.read_text(encoding="utf-8"))
    assert load_payload["status"] == "PASS"
    assert load_payload["evidence"]["strict_state_load"] is True

    verify_request = tmp_path / "verify_request.json"
    verify_response = tmp_path / "verify_response.json"
    verify_request.write_text(
        json.dumps(
            {
                "operation": "verify_roundtrip",
                "source_root": str(source_root),
                "output_dir": str(tmp_path / "verify"),
                "before_prediction_path": fit_payload["artifacts"]["prediction_before"],
                "after_prediction_path": load_payload["artifacts"]["prediction_after"],
            }
        ),
        encoding="utf-8",
    )
    third = subprocess.run(
        [
            sys.executable,
            str(script),
            "--request",
            str(verify_request),
            "--response",
            str(verify_response),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert third.returncode == 0, third.stderr
    verification = json.loads(verify_response.read_text(encoding="utf-8"))
    assert verification["status"] == "PASS"
    assert verification["evidence"]["equal_within_tolerance"] is True
