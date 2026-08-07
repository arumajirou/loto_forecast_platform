from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.auto_campaign.persistence import sha256_file, write_json, write_sha256s
from loto.auto_campaign.prediction_lock import (
    PREDICTION_LOCK_PATH,
    freeze_prospective_predictions,
    verify_prediction_lock,
)


def _prospective_run(tmp_path: Path) -> Path:
    root = tmp_path / "prospective"
    task = root / "tasks" / "AutoTFT" / "p1"
    bundle = task / "best_model"
    bundle.mkdir(parents=True)

    before = bundle / "prediction_before_save.parquet"
    after = bundle / "prediction_after_load.parquet"
    before.write_bytes(b"stable-prediction-before")
    after.write_bytes(b"stable-prediction-after")
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
            "prediction_sha256": sha256_file(before),
            "task": {"stage": "prospective", "model_name": "AutoTFT"},
        },
    )
    write_json(
        task / "manifest.json",
        {
            "status": "PASS",
            "task": {"stage": "prospective", "model_name": "AutoTFT"},
        },
    )
    write_sha256s(task)

    write_json(root / "campaign_config.json", {"seed": 1, "stage": "prospective"})
    write_json(root / "data_contract.json", {"status": "PASS", "rows": 100})
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
            "run_id": "prospective-test",
            "planned_tasks": 1,
            "completed_tasks": 1,
            "failed_tasks": 0,
            "code_sha256": "code-v1",
            "data_sha256": "data-v1",
            "promotion_gate_status": "PASS",
            "promotion_gate_path": "PROMOTION_GATE.json",
            "lineage_status": "PASS",
            "lineage_path": "LINEAGE.json",
            "lineage_chain_sha256": "lineage-chain-v1",
        },
    )
    write_sha256s(root)
    return root


def _manifest(root: Path) -> dict[str, object]:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def test_freeze_and_verify_campaign_prediction_lock(tmp_path: Path) -> None:
    root = _prospective_run(tmp_path)

    result = freeze_prospective_predictions(root)
    verified = verify_prediction_lock(root, _manifest(root))

    assert result["status"] == "PASS"
    assert result["prediction_lock_status"] == "LOCKED"
    assert result["prediction_task_count"] == 1
    assert result["idempotent"] is False
    assert (root / PREDICTION_LOCK_PATH).is_file()
    assert verified["status"] == "PASS"
    assert verified["task_count"] == 1
    assert verified["timestamp_authority"] == "LOCAL_SYSTEM_UTC"


def test_second_freeze_is_idempotent_and_preserves_lock_bytes(tmp_path: Path) -> None:
    root = _prospective_run(tmp_path)
    first = freeze_prospective_predictions(root)
    before = (root / PREDICTION_LOCK_PATH).read_bytes()

    second = freeze_prospective_predictions(root)

    assert first["prediction_lock_sha256"] == second["prediction_lock_sha256"]
    assert second["idempotent"] is True
    assert (root / PREDICTION_LOCK_PATH).read_bytes() == before


def test_prediction_mutation_invalidates_lock(tmp_path: Path) -> None:
    root = _prospective_run(tmp_path)
    freeze_prospective_predictions(root)
    prediction = root / "tasks/AutoTFT/p1/best_model/prediction_before_save.parquet"
    prediction.write_bytes(b"mutated-after-lock")
    write_sha256s(root)

    verified = verify_prediction_lock(root, _manifest(root))

    assert verified["status"] == "FAIL"
    assert any("prediction_before SHA256 mismatch" in item for item in verified["failures"])
    with pytest.raises(ValueError, match="existing prediction lock is invalid"):
        freeze_prospective_predictions(root)


def test_actual_artifact_blocks_lock_creation(tmp_path: Path) -> None:
    root = _prospective_run(tmp_path)
    write_json(root / "verified_actual_values.json", {"actual": [1, 2, 3]})
    write_sha256s(root)

    with pytest.raises(ValueError, match="actual-bearing artifact present"):
        freeze_prospective_predictions(root)

    assert not (root / PREDICTION_LOCK_PATH).exists()


def test_missing_task_freeze_blocks_lock_creation(tmp_path: Path) -> None:
    root = _prospective_run(tmp_path)
    (root / "tasks/AutoTFT/p1/prediction_freeze.json").unlink()
    write_sha256s(root / "tasks/AutoTFT/p1")
    write_sha256s(root)

    with pytest.raises(ValueError, match="no task prediction_freeze.json files found"):
        freeze_prospective_predictions(root)

    assert not (root / PREDICTION_LOCK_PATH).exists()


def test_sealed_run_cannot_receive_retroactive_lock(tmp_path: Path) -> None:
    root = _prospective_run(tmp_path)
    write_json(root / "VERIFICATION_SEAL.json", {"status": "PASS"})
    write_sha256s(root)

    with pytest.raises(ValueError, match="sealed prospective run cannot receive"):
        freeze_prospective_predictions(root)

    assert not (root / PREDICTION_LOCK_PATH).exists()


def test_nonprospective_run_without_lock_is_not_applicable(tmp_path: Path) -> None:
    root = tmp_path / "holdout"
    root.mkdir()

    result = verify_prediction_lock(root, {"status": "PASS", "stage": "holdout"})

    assert result["status"] == "NOT_APPLICABLE"
    assert result["failures"] == []
