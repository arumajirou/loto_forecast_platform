from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from loto.auto_campaign.persistence import sha256_file, write_json, write_sha256s
from loto.auto_campaign.prediction_lock import freeze_prospective_predictions
from loto.auto_campaign.prospective_baselines import BASELINE_NAMES
from loto.auto_campaign.prospective_scoring import score_locked_prospective_run
from loto.auto_campaign.prospective_scoring_verification import (
    verify_prospective_scoring,
)
from loto.auto_campaign.verification_seal import write_verification_seal

NUMBER_COLUMNS = ["P1", "P2", "P3", "P4", "P5"]


def _history(path: Path) -> Path:
    pd.DataFrame(
        [
            {
                "draw_id": "D1",
                "draw_index": 1,
                "P1": 1,
                "P2": 5,
                "P3": 10,
                "P4": 20,
                "P5": 28,
            },
            {
                "draw_id": "D2",
                "draw_index": 2,
                "P1": 2,
                "P2": 6,
                "P3": 11,
                "P4": 21,
                "P5": 29,
            },
            {
                "draw_id": "D3",
                "draw_index": 3,
                "P1": 3,
                "P2": 7,
                "P3": 12,
                "P4": 22,
                "P5": 30,
            },
        ]
    ).to_csv(path, index=False)
    return path


def _actuals(path: Path, *, draw_index: int = 4) -> Path:
    pd.DataFrame(
        [
            {
                "draw_id": f"D{draw_index}",
                "draw_index": draw_index,
                "P1": 4,
                "P2": 8,
                "P3": 13,
                "P4": 23,
                "P5": 31,
            }
        ]
    ).to_csv(path, index=False)
    return path


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def _locked_source(tmp_path: Path, history: Path) -> Path:
    root = tmp_path / "prospective"
    task = root / "tasks" / "AutoTFT" / "u_shared" / "seed_1" / "ray"
    bundle = task / "best_model"
    bundle.mkdir(parents=True)
    task_payload = {
        "stage": "prospective",
        "model_name": "AutoTFT",
        "track": "u_shared",
        "position": None,
        "seed": 1,
        "fold": None,
        "origin": None,
        "backend": "ray",
        "config_index": None,
    }
    prediction = pd.DataFrame(
        {
            "unique_id": NUMBER_COLUMNS,
            "ds": [4] * 5,
            "AutoTFT_u_shared_s1": [4.1, 8.2, 12.4, 23.4, 30.7],
        }
    )
    prediction.to_parquet(bundle / "prediction_before_save.parquet", index=False)
    prediction.to_parquet(bundle / "prediction_after_load.parquet", index=False)
    write_json(
        bundle / "load_predict_verification.json",
        {
            "status": "PASS",
            "loaded": True,
            "predicted": True,
            "shape_match": True,
            "finite": True,
            "prediction_match": True,
            "cpu_fallback": False,
        },
    )
    write_json(bundle / "manifest.json", {"status": "PASS"})
    write_sha256s(bundle)
    write_json(
        task / "prediction_freeze.json",
        {
            "frozen_at": "2026-08-05T07:00:00+00:00",
            "actual_known": False,
            "prediction_sha256": sha256_file(bundle / "prediction_before_save.parquet"),
            "task": task_payload,
        },
    )
    write_json(task / "manifest.json", {"status": "PASS", "task": task_payload})
    write_sha256s(task)

    write_json(
        root / "campaign_config.json",
        {
            "number_columns": NUMBER_COLUMNS,
            "draw_id_candidates": ["draw_id"],
            "draw_index_candidates": ["draw_index"],
        },
    )
    write_json(
        root / "data_contract.json",
        {
            "status": "PASS",
            "rows": 3,
            "draws": 3,
            "first_draw_index": 1,
            "last_draw_index": 3,
            "number_columns": NUMBER_COLUMNS,
            "draw_id_column": "draw_id",
            "draw_index_column": "draw_index",
        },
    )
    write_json(
        root / "PROMOTION_GATE.json",
        {
            "schema_version": "all-auto-promotion-gate-v1",
            "status": "PASS",
            "target_stage": "prospective",
        },
    )
    write_json(
        root / "LINEAGE.json",
        {
            "schema_version": "all-auto-lineage-v1",
            "status": "PASS",
            "target_stage": "prospective",
            "chain_sha256": "lineage-chain-v1",
        },
    )
    write_json(
        root / "manifest.json",
        {
            "schema_version": "all-auto-campaign-run-v1",
            "status": "PASS",
            "stage": "prospective",
            "run_id": "prospective-scoring-test",
            "planned_tasks": 1,
            "completed_tasks": 1,
            "failed_tasks": 0,
            "code_sha256": "model-code-v1",
            "data_sha256": sha256_file(history),
            "promotion_gate_status": "PASS",
            "promotion_gate_path": "PROMOTION_GATE.json",
            "lineage_status": "PASS",
            "lineage_path": "LINEAGE.json",
            "lineage_chain_sha256": "lineage-chain-v1",
        },
    )
    write_sha256s(root)
    freeze_prospective_predictions(root)
    verification_result = {
        "status": "PASS",
        "run_manifest_status": "PASS",
        "coverage_state_verification": {"status": "PASS"},
        "promotion_gate_verification": {"status": "PASS"},
        "lineage_verification": {"status": "PASS"},
        "prediction_lock_verification": {"status": "PASS"},
        "failures": [],
    }
    write_json(root / "VERIFICATION_REPORT.json", verification_result)
    write_verification_seal(root, verification_result)
    write_sha256s(root)
    return root


def test_score_locked_run_is_self_contained_and_source_immutable(tmp_path: Path) -> None:
    history = _history(tmp_path / "history.csv")
    actuals = _actuals(tmp_path / "actuals.csv")
    source = _locked_source(tmp_path, history)
    before = _tree_hashes(source)
    output = tmp_path / "scoring"

    result = score_locked_prospective_run(
        run_root=source,
        actuals_path=actuals,
        history_path=history,
        output=output,
        random_seed=1,
        actual_source_label="synthetic fixture",
    )
    verified = verify_prospective_scoring(output)

    assert result["status"] == "PASS"
    assert result["verification_status"] == "PASS"
    assert verified["status"] == "PASS"
    assert _tree_hashes(source) == before
    metrics = pd.read_parquet(output / "METRICS.parquet")
    required = {"hit_pm1", "all_positions_hit_pm1", "mae", "mse", "rmse"}
    assert required.issubset(metrics.columns)
    baselines = pd.read_parquet(output / "BASELINE_PREDICTIONS.parquet")
    assert set(baselines["baseline_name"]) == set(BASELINE_NAMES)
    report = json.loads((output / "SCORING_REPORT.json").read_text(encoding="utf-8"))
    assert report["priority_metric"] == "hit_pm1"
    assert report["baseline_count"] == len(BASELINE_NAMES)

    shutil.rmtree(source)
    relocated = verify_prospective_scoring(output)
    assert relocated["status"] == "PASS"
    assert relocated["source_reverification"] == "NOT_AVAILABLE"


def test_scoring_artifact_mutation_is_detected(tmp_path: Path) -> None:
    history = _history(tmp_path / "history.csv")
    actuals = _actuals(tmp_path / "actuals.csv")
    source = _locked_source(tmp_path, history)
    output = tmp_path / "scoring"
    score_locked_prospective_run(
        run_root=source,
        actuals_path=actuals,
        history_path=history,
        output=output,
    )
    (output / "METRICS.parquet").write_bytes(b"mutated")

    verified = verify_prospective_scoring(output)

    assert verified["status"] == "FAIL"
    assert any("SHA256SUMS mismatch: METRICS.parquet" in item for item in verified["failures"])


def test_history_hash_mismatch_is_rejected_before_output_creation(tmp_path: Path) -> None:
    history = _history(tmp_path / "history.csv")
    actuals = _actuals(tmp_path / "actuals.csv")
    source = _locked_source(tmp_path, history)
    history.write_text(history.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    output = tmp_path / "scoring"

    with pytest.raises(ValueError, match="history SHA-256 differs"):
        score_locked_prospective_run(
            run_root=source,
            actuals_path=actuals,
            history_path=history,
            output=output,
        )

    assert not output.exists()


def test_actual_horizon_mismatch_is_rejected(tmp_path: Path) -> None:
    history = _history(tmp_path / "history.csv")
    actuals = _actuals(tmp_path / "actuals.csv", draw_index=5)
    source = _locked_source(tmp_path, history)

    with pytest.raises(ValueError, match="actual draw indices differ"):
        score_locked_prospective_run(
            run_root=source,
            actuals_path=actuals,
            history_path=history,
            output=tmp_path / "scoring",
        )
