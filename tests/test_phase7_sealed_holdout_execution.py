from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_DIR = REPO / "tools" / "phase7_holdout_runner"
MODULE_PATH = MODULE_DIR / "sealed_holdout_execution.py"
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location("phase7_sealed_holdout_execution", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_validate_completed_artifacts_requires_50_lock_chain_and_evaluation(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    lock_root = artifacts / "prediction_locks"
    lock_root.mkdir(parents=True)

    chain_rows = []
    for draw in range(1, 51):
        lock = lock_root / f"draw-{draw:03d}.json"
        lock.write_text(
            json.dumps({"draw": draw, "prediction": [1, 2, 3]}) + "\n",
            encoding="utf-8",
        )
        chain_rows.append({"draw": draw, "lock_sha256": MOD.sha256_file(lock)})

    (artifacts / "SEQUENTIAL_LOCK_CHAIN.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in chain_rows),
        encoding="utf-8",
    )
    (artifacts / "PRE_SCORE_SEAL.json").write_text(
        json.dumps({"status": "SEALED"}) + "\n",
        encoding="utf-8",
    )
    (artifacts / "progress.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "holdout_draws_done": 50,
                "actuals_accessed": 50,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (artifacts / "metrics.json").write_text(
        json.dumps(
            {
                "hit_at_1": 0.4,
                "position_hit_at_1": [0.4, 0.4, 0.4],
                "all_position_hit_at_1": 0.1,
                "mae": 2.0,
                "mse": 5.0,
                "rmse": 2.236,
                "baselines": [
                    "random",
                    "fixed",
                    "mean",
                    "median",
                    "last",
                    "frequency",
                    "statistical_ar1",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = MOD.validate_completed_artifacts(artifacts)
    assert result["holdout_draws_done"] == 50
    assert result["actuals_accessed"] == 50
    assert result["prediction_lock_count"] == 50
    assert result["sequential_chain_records"] == 50


def test_prior_lock_blocks_any_second_holdout_execution(tmp_path: Path) -> None:
    prior = tmp_path / "phase7-sealed-holdout-v1-existing"
    lock_root = prior / "artifacts" / "prediction_locks"
    lock_root.mkdir(parents=True)
    (lock_root / "draw-001.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(MOD.HoldoutExecutionError, match="refusing rerun"):
        MOD.ensure_no_prior_holdout_execution(tmp_path)


def test_execution_contract_never_disables_lock_before_actual() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "--stop-after-replay" not in text
    assert '"safe_to_read_actuals_before_prediction_lock": False' in text
    assert '"safe_to_reselect_model": False' in text
    assert "EXPECTED_DERIVED_RUNNER_SHA256" in text
    assert "run_preflight" in text
    assert "ensure_no_prior_holdout_execution" in text
