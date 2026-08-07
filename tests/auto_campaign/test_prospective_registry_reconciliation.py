from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from loto.auto_campaign import prospective_registry_reconciliation_expected as expected_module
from loto.auto_campaign.persistence import (
    sha256_file,
    write_json,
    write_sha256s,
)
from loto.auto_campaign.prospective_registry_contract import (
    BACKEND_RECEIPTS,
    REGISTRY_MANIFEST,
    REGISTRY_PAYLOAD,
    REGISTRY_REPORT,
    REGISTRY_SCHEMA_VERSION,
    _canonical_sha256,
)
from loto.auto_campaign.prospective_registry_payload import (
    _registry_file_inventory,
)
from loto.auto_campaign.prospective_registry_reconciliation import (
    ReconciliationBackendFunctions,
    ReconciliationOptions,
    _compare_mlflow,
    _compare_postgres,
    reconcile_prospective_registry,
    verify_registry_reconciliation,
)


def _expected() -> dict[str, Any]:
    candidate = {
        "registry_id": "registry-1",
        "candidate_key": "model|AutoTFT|NONE|u_shared",
        "source_type": "model",
        "model_name": "AutoTFT",
        "baseline_name": None,
        "track": "u_shared",
        "seed_count": 1,
        "hit_pm1_mean": 0.8,
        "hit_pm1_var": 0.0,
        "hit_pm1_min": 0.8,
        "hit_pm1_max": 0.8,
        "all_positions_hit_pm1_mean": 0.2,
        "mae_mean": 1.0,
        "mse_mean": 2.0,
        "rmse_mean": 1.414,
        "worst_seed_hit_pm1": 0.8,
        "rank": 1,
    }
    seed = {
        "registry_id": "registry-1",
        "candidate_key": candidate["candidate_key"],
        "seed_token": "1",
        "seed": 1,
        "source_type": "model",
        "model_name": "AutoTFT",
        "baseline_name": None,
        "track": "u_shared",
        "hit_pm1": 0.8,
        "all_positions_hit_pm1": 0.2,
        "mae": 1.0,
        "mse": 2.0,
        "rmse": 1.414,
    }
    position = {
        "registry_id": "registry-1",
        "row_key": "position-row-1",
        "candidate_key": candidate["candidate_key"],
        "seed_token": "1",
        "unique_id": "P1",
        "variant": "reconciled",
        "hit_pm1": 1.0,
        "exact_hit": 1.0,
        "mae": 0.0,
        "mse": 0.0,
        "rmse": 0.0,
    }
    expected = {
        "schema_version": "all-auto-prospective-registry-reconciliation-v1",
        "registry_id": "registry-1",
        "registry_namespace": "production",
        "scoring_id": "score-1",
        "payload_sha256": "a" * 64,
        "created_at": "2026-08-05T00:00:00+00:00",
        "source": {
            "prediction_lock_sha256": "b" * 64,
            "scoring_report_sha256": "c" * 64,
            "artifact_manifest_sha256": "d" * 64,
            "scoring_sha256s_sha256": "e" * 64,
        },
        "counts": {
            "candidate_count": 1,
            "seed_metric_rows": 1,
            "position_metric_rows": 1,
            "artifact_rows": 1,
        },
        "backend_policy": {
            "postgres_dsn_env": "TEST_POSTGRES_DSN",
            "mlflow_uri_env": "TEST_MLFLOW_URI",
            "mlflow_experiment": "test-experiment",
            "artifact_mode": "metadata",
        },
        "receipt_mlflow_parent_run_id": "parent-1",
        "candidates": [candidate],
        "seed_metrics": [seed],
        "position_metrics": [position],
        "artifacts": [
            {
                "registry_id": "registry-1",
                "path": "SCORING_REPORT.json",
                "size_bytes": 10,
                "sha256": "f" * 64,
            }
        ],
        "mlflow_artifacts": [
            {
                "path": "registry_evidence/REGISTRY_PAYLOAD.json",
                "sha256": "1" * 64,
            }
        ],
    }
    expected["expected_sha256"] = _canonical_sha256(expected)
    return expected


def _valid_registry_receipt(
    root: Path,
    expected: dict[str, Any],
) -> Path:
    """Create the smallest registry receipt accepted by the real verifier."""

    root.mkdir()

    receipts = {
        "postgres_prepare": {
            "backend": "postgres",
            "status": "PASS",
            "phase": "PREPARED",
        },
        "mlflow": {
            "backend": "mlflow",
            "status": "PASS",
            "parent_run_id": "parent-1",
        },
        "postgres_finalize": {
            "backend": "postgres",
            "status": "PASS",
            "phase": "FINALIZED",
            "mlflow_parent_run_id": "parent-1",
        },
    }

    payload = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "registry_id": expected["registry_id"],
        "registry_namespace": expected["registry_namespace"],
        "scoring_id": expected["scoring_id"],
        "created_at": expected["created_at"],
        "source": {
            # Deliberately unavailable. The registry verifier records
            # source_reverification=NOT_AVAILABLE without weakening
            # receipt integrity verification.
            "scoring_root": str(root.parent / "unavailable-source-scoring"),
        },
        "metric_policy": {
            "priority_metric": "hit_pm1",
            "secondary_metrics": [
                "all_positions_hit_pm1",
                "mae",
                "mse",
                "rmse",
            ],
            "aggregation": [
                "per_seed",
                "mean",
                "variance",
                "minimum",
                "maximum",
                "worst_seed",
            ],
            "best_seed_only_selection": False,
        },
        "backend_policy": {
            "required_backends": ["postgres", "mlflow"],
        },
        "counts": dict(expected["counts"]),
        "scoring_report": {},
    }

    payload["payload_sha256"] = _canonical_sha256(payload)

    write_json(
        root / REGISTRY_PAYLOAD,
        payload,
    )

    backend_receipts = {
        "attempted": sorted(receipts),
        "receipts": receipts,
    }

    write_json(
        root / BACKEND_RECEIPTS,
        backend_receipts,
    )

    report = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "status": "PASS",
        "registry_id": expected["registry_id"],
        "registry_namespace": expected["registry_namespace"],
        "scoring_id": expected["scoring_id"],
        "payload_sha256": payload["payload_sha256"],
        "source_reverification": "NOT_AVAILABLE",
        "receipts": receipts,
        "source_evidence": [],
        "safety": {
            "source_scoring_mutated": False,
            "automatic_promotion": False,
            "automatic_retraining": False,
            "best_seed_only_selection": False,
            "secrets_persisted": False,
        },
    }

    write_json(
        root / REGISTRY_REPORT,
        report,
    )

    manifest = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "status": "PASS",
        "registry_id": expected["registry_id"],
        "scoring_id": expected["scoring_id"],
        "payload_sha256": payload["payload_sha256"],
        "registry_report_sha256": sha256_file(root / REGISTRY_REPORT),
        "backend_receipts_sha256": sha256_file(root / BACKEND_RECEIPTS),
        "files": _registry_file_inventory(root),
    }

    manifest["manifest_sha256"] = _canonical_sha256(manifest)

    write_json(
        root / REGISTRY_MANIFEST,
        manifest,
    )

    write_sha256s(root)

    return root


def _postgres(expected: dict[str, Any]) -> dict[str, Any]:
    source = expected["source"]
    return {
        "backend": "postgres",
        "status": "PASS",
        "run_rows": [
            {
                "registry_id": expected["registry_id"],
                "scoring_id": expected["scoring_id"],
                "registry_namespace": expected["registry_namespace"],
                "status": "PASS",
                "prediction_lock_sha256": source["prediction_lock_sha256"],
                "scoring_report_sha256": source["scoring_report_sha256"],
                "artifact_manifest_sha256": source["artifact_manifest_sha256"],
                "scoring_sha256s_sha256": source["scoring_sha256s_sha256"],
                "payload_sha256": expected["payload_sha256"],
                "mlflow_experiment": "test-experiment",
                "mlflow_parent_run_id": "parent-1",
            }
        ],
        "candidates": [dict(expected["candidates"][0])],
        "seed_metrics": [dict(expected["seed_metrics"][0])],
        "position_metrics": [dict(expected["position_metrics"][0])],
        "artifacts": [dict(expected["artifacts"][0])],
    }


def _mlflow(expected: dict[str, Any]) -> dict[str, Any]:
    seed = expected["seed_metrics"][0]
    return {
        "backend": "mlflow",
        "status": "PASS",
        "parent_runs": [
            {
                "run_id": "parent-1",
                "status": "FINISHED",
                "tags": {
                    "registry_id": expected["registry_id"],
                    "registry_role": "parent",
                    "payload_sha256": expected["payload_sha256"],
                    "scoring_id": expected["scoring_id"],
                },
                "params": {
                    "registry_id": expected["registry_id"],
                    "scoring_id": expected["scoring_id"],
                    "registry_namespace": expected["registry_namespace"],
                    "payload_sha256": expected["payload_sha256"],
                    "priority_metric": "hit_pm1",
                },
                "metrics": {},
            }
        ],
        "child_runs": [
            {
                "run_id": "child-1",
                "status": "FINISHED",
                "tags": {
                    "candidate_key": seed["candidate_key"],
                    "seed_token": seed["seed_token"],
                    "mlflow.parentRunId": "parent-1",
                    "payload_sha256": expected["payload_sha256"],
                },
                "params": {},
                "metrics": {
                    name: seed[name]
                    for name in (
                        "hit_pm1",
                        "all_positions_hit_pm1",
                        "mae",
                        "mse",
                        "rmse",
                    )
                },
            }
        ],
        "artifacts": [dict(expected["mlflow_artifacts"][0])],
    }


def test_backend_snapshots_match_expected_contract() -> None:
    expected = _expected()

    assert _compare_postgres(expected, _postgres(expected), 1e-12) == []
    assert (
        _compare_mlflow(
            expected,
            _mlflow(expected),
            1e-12,
            require_remote_artifacts=True,
        )
        == []
    )


def test_postgres_duplicate_and_metric_drift_are_detected() -> None:
    expected = _expected()
    snapshot = _postgres(expected)
    snapshot["candidates"].append(dict(snapshot["candidates"][0]))
    snapshot["candidates"][0]["hit_pm1_mean"] = 0.1

    failures = _compare_postgres(expected, snapshot, 1e-12)

    assert any("duplicate key" in item for item in failures)
    assert any("hit_pm1_mean" in item for item in failures)


def test_mlflow_missing_child_parent_and_artifact_drift_are_detected() -> None:
    expected = _expected()
    snapshot = _mlflow(expected)
    snapshot["parent_runs"][0]["run_id"] = "wrong-parent"
    snapshot["child_runs"] = []
    snapshot["artifacts"][0]["sha256"] = "0" * 64

    failures = _compare_mlflow(
        expected,
        snapshot,
        1e-12,
        require_remote_artifacts=True,
    )

    assert any("parent run ID differs" in item for item in failures)
    assert any("child missing" in item for item in failures)
    assert any("MLflow artifacts mismatch" in item for item in failures)


def test_reconciliation_pass_is_self_contained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _expected()
    receipt = _valid_registry_receipt(
        tmp_path / "receipt",
        expected,
    )
    output = tmp_path / "reconciliation"
    calls: list[str] = []

    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry_reconciliation.verify_prospective_registry",
        lambda _root: {"status": "PASS", "failures": []},
    )
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry_reconciliation._expected_snapshot",
        lambda _root: expected,
    )
    monkeypatch.setenv("TEST_POSTGRES_DSN", "postgresql://user:secret@db/loto")
    monkeypatch.setenv("TEST_MLFLOW_URI", "http://mlflow:5000")

    def postgres(_dsn: str, _expected_value: dict[str, Any]) -> dict[str, Any]:
        calls.append("postgres")
        return _postgres(expected)

    def mlflow(
        _uri: str,
        _experiment: str,
        _expected_value: dict[str, Any],
        *,
        require_remote_artifacts: bool,
    ) -> dict[str, Any]:
        assert require_remote_artifacts is True
        calls.append("mlflow")
        return _mlflow(expected)

    result = reconcile_prospective_registry(
        receipt_root=receipt,
        output=output,
        options=ReconciliationOptions(),
        backends=ReconciliationBackendFunctions(postgres, mlflow),
    )

    assert result["status"] == "PASS"
    assert result["integrity_status"] == "PASS"
    assert calls == ["postgres", "mlflow"]
    assert verify_registry_reconciliation(output)["status"] == "PASS"
    shutil.rmtree(receipt)
    assert verify_registry_reconciliation(output)["status"] == "PASS"


def test_reconciliation_distinguishes_drift_from_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _expected()
    receipt = _valid_registry_receipt(
        tmp_path / "receipt",
        expected,
    )
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry_reconciliation.verify_prospective_registry",
        lambda _root: {"status": "PASS", "failures": []},
    )
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry_reconciliation._expected_snapshot",
        lambda _root: expected,
    )
    monkeypatch.setenv("TEST_POSTGRES_DSN", "postgresql://db/loto")
    monkeypatch.setenv("TEST_MLFLOW_URI", "http://mlflow:5000")
    drifted = _postgres(expected)
    drifted["run_rows"][0]["payload_sha256"] = "wrong"

    drift = reconcile_prospective_registry(
        receipt_root=receipt,
        output=tmp_path / "drift",
        options=ReconciliationOptions(),
        backends=ReconciliationBackendFunctions(
            lambda _dsn, _expected_value: drifted,
            lambda *_args, **_kwargs: _mlflow(expected),
        ),
    )
    assert drift["status"] == "DRIFT"
    assert drift["drift_failures"]

    monkeypatch.delenv("TEST_POSTGRES_DSN")
    blocked = reconcile_prospective_registry(
        receipt_root=receipt,
        output=tmp_path / "blocked",
        options=ReconciliationOptions(),
        backends=ReconciliationBackendFunctions(
            lambda _dsn, _expected_value: _postgres(expected),
            lambda *_args, **_kwargs: _mlflow(expected),
        ),
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["backend_errors"]


def test_output_inside_source_is_rejected_before_parent_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = tmp_path / "receipt"
    receipt.mkdir()
    target_parent = receipt / "new-directory"
    target = target_parent / "reconciliation"
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry_reconciliation.verify_prospective_registry",
        lambda _root: {"status": "PASS", "failures": []},
    )

    with pytest.raises(ValueError, match="outside the registry receipt"):
        reconcile_prospective_registry(
            receipt_root=receipt,
            output=target,
            options=ReconciliationOptions(),
        )

    assert not target_parent.exists()


def test_reconciliation_mutation_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _expected()
    receipt = _valid_registry_receipt(
        tmp_path / "receipt",
        expected,
    )
    output = tmp_path / "reconciliation"
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry_reconciliation.verify_prospective_registry",
        lambda _root: {"status": "PASS", "failures": []},
    )
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry_reconciliation._expected_snapshot",
        lambda _root: expected,
    )
    monkeypatch.setenv("TEST_POSTGRES_DSN", "postgresql://db/loto")
    monkeypatch.setenv("TEST_MLFLOW_URI", "http://mlflow:5000")
    reconcile_prospective_registry(
        receipt_root=receipt,
        output=output,
        options=ReconciliationOptions(),
        backends=ReconciliationBackendFunctions(
            lambda _dsn, _expected_value: _postgres(expected),
            lambda *_args, **_kwargs: _mlflow(expected),
        ),
    )
    (output / "POSTGRES_SNAPSHOT.json").write_text("{}\n", encoding="utf-8")

    verified = verify_registry_reconciliation(output)

    assert verified["status"] == "FAIL"
    assert verified["failures"]


def test_expected_snapshot_builds_real_expected_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Frame:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self.rows = rows

        def to_dict(
            self,
            *,
            orient: str,
        ) -> list[dict[str, Any]]:
            assert orient == "records"
            return self.rows

    payload = {
        "registry_id": "registry-1",
        "registry_namespace": "production",
        "scoring_id": "score-1",
        "payload_sha256": "a" * 64,
        "created_at": "2026-08-05T00:00:00+00:00",
        "source": {
            "prediction_lock_sha256": "b" * 64,
            "scoring_report_sha256": "c" * 64,
            "artifact_manifest_sha256": "d" * 64,
            "scoring_sha256s_sha256": "e" * 64,
        },
        "counts": {
            "candidate_count": 1,
            "seed_metric_rows": 1,
            "position_metric_rows": 1,
            "artifact_rows": 1,
        },
        "backend_policy": {
            "postgres_dsn_env": "TEST_POSTGRES_DSN",
            "mlflow_uri_env": "TEST_MLFLOW_URI",
            "mlflow_experiment": "test-experiment",
            "artifact_mode": "metadata",
        },
    }

    documents = {
        "REGISTRY_PAYLOAD.json": payload,
        "REGISTRY_REPORT.json": {
            "status": "PASS",
        },
        "BACKEND_RECEIPTS.json": {
            "receipts": {
                "mlflow": {
                    "parent_run_id": "parent-1",
                },
                "postgres_finalize": {
                    "mlflow_parent_run_id": "parent-1",
                },
            },
        },
    }

    monkeypatch.setattr(
        expected_module,
        "_read_json",
        lambda path, _label: documents[path.name],
    )

    monkeypatch.setattr(
        expected_module,
        "_read_registry_tables",
        lambda _root: {
            "seed_summary": object(),
            "ranking": object(),
            "seed_metrics": object(),
            "position_metrics": object(),
        },
    )

    monkeypatch.setattr(
        expected_module,
        "_candidate_frame",
        lambda *_args: _Frame([{"candidate_key": "candidate-1"}]),
    )

    monkeypatch.setattr(
        expected_module,
        "_seed_metric_frame",
        lambda *_args: _Frame([{"candidate_key": "candidate-1", "seed": 1}]),
    )

    monkeypatch.setattr(
        expected_module,
        "_position_metric_frame",
        lambda *_args: _Frame(
            [
                {
                    "candidate_key": "candidate-1",
                    "position": "P1",
                }
            ]
        ),
    )

    monkeypatch.setattr(
        expected_module,
        "_expected_artifacts",
        lambda *_args: [
            {
                "registry_id": "registry-1",
                "path": "SCORING_REPORT.json",
                "size_bytes": 1,
                "sha256": "f" * 64,
            }
        ],
    )

    monkeypatch.setattr(
        expected_module,
        "sha256_file",
        lambda _path: "9" * 64,
    )

    monkeypatch.setattr(
        expected_module.pd,
        "DataFrame",
        lambda rows: _Frame(list(rows)),
    )

    result = expected_module._expected_snapshot(tmp_path)

    assert result["schema_version"] == "all-auto-prospective-registry-reconciliation-v1"
    assert result["registry_id"] == "registry-1"
    assert result["receipt_mlflow_parent_run_id"] == "parent-1"
    assert result["candidates"] == [{"candidate_key": "candidate-1"}]
    assert len(result["expected_sha256"]) == 64
