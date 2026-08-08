from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from loto.auto_campaign.persistence import sha256_file, write_json, write_sha256s
from loto.auto_campaign.prospective_registry import (
    RegistryBackendFunctions,
    RegistryOptions,
    _position_metric_frame,
    _safe_error,
    register_prospective_scoring,
    verify_prospective_registry,
)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }


def _write_table(frame: pd.DataFrame, root: Path, stem: str) -> None:
    frame.to_parquet(root / f"{stem}.parquet", index=False)
    frame.to_csv(root / f"{stem}.csv", index=False)


def _scoring_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "scoring"
    source_evidence = root / "source_evidence"
    source_evidence.mkdir(parents=True)
    model_seed = {
        "source_type": "model",
        "model_name": "AutoTFT",
        "baseline_name": None,
        "track": "u_shared",
        "seed": 1,
        "hit_pm1": 0.8,
        "all_positions_hit_pm1": 0.5,
        "mae": 1.0,
        "mse": 2.0,
        "rmse": 2.0**0.5,
    }
    baseline_seed = {
        "source_type": "baseline",
        "model_name": None,
        "baseline_name": "last",
        "track": "baseline",
        "seed": None,
        "hit_pm1": 0.4,
        "all_positions_hit_pm1": 0.0,
        "mae": 2.0,
        "mse": 5.0,
        "rmse": 5.0**0.5,
    }
    per_seed = pd.DataFrame([model_seed, baseline_seed])
    summary_rows = []
    for row in (model_seed, baseline_seed):
        summary_rows.append(
            {
                "source_type": row["source_type"],
                "model_name": row["model_name"],
                "baseline_name": row["baseline_name"],
                "track": row["track"],
                "hit_pm1_mean": row["hit_pm1"],
                "hit_pm1_std": None,
                "hit_pm1_var": None,
                "hit_pm1_min": row["hit_pm1"],
                "hit_pm1_max": row["hit_pm1"],
                "all_positions_hit_pm1_mean": row["all_positions_hit_pm1"],
                "all_positions_hit_pm1_std": None,
                "all_positions_hit_pm1_var": None,
                "all_positions_hit_pm1_min": row["all_positions_hit_pm1"],
                "all_positions_hit_pm1_max": row["all_positions_hit_pm1"],
                "mae_mean": row["mae"],
                "mae_std": None,
                "mae_var": None,
                "mae_min": row["mae"],
                "mae_max": row["mae"],
                "mse_mean": row["mse"],
                "mse_std": None,
                "mse_var": None,
                "mse_min": row["mse"],
                "mse_max": row["mse"],
                "rmse_mean": row["rmse"],
                "rmse_std": None,
                "rmse_var": None,
                "rmse_min": row["rmse"],
                "rmse_max": row["rmse"],
                "seed_count": 1,
                "worst_seed_hit_pm1": row["hit_pm1"],
            }
        )
    seed_summary = pd.DataFrame(summary_rows)
    ranking = seed_summary.copy()
    ranking.insert(0, "rank", [1, 2])
    position = pd.DataFrame(
        [
            {
                "candidate_id": "task:model",
                "source_type": "model",
                "model_name": "AutoTFT",
                "baseline_name": None,
                "track": "u_shared",
                "position": None,
                "seed": 1,
                "backend": "ray",
                "config_index": 0,
                "variant": "reconciled",
                "unique_id": "P1",
                "hit_pm1": 1.0,
                "exact_hit": 1.0,
                "mae": 0.0,
                "mse": 0.0,
                "rmse": 0.0,
            },
            {
                "candidate_id": "baseline:last",
                "source_type": "baseline",
                "model_name": None,
                "baseline_name": "last",
                "track": "baseline",
                "position": None,
                "seed": None,
                "backend": "numpy",
                "config_index": None,
                "variant": "reconciled",
                "unique_id": "P1",
                "hit_pm1": 0.0,
                "exact_hit": 0.0,
                "mae": 2.0,
                "mse": 4.0,
                "rmse": 2.0,
            },
        ]
    )
    comparison = pd.DataFrame(
        [
            {
                "champion_model": "AutoTFT",
                "champion_track": "u_shared",
                "baseline": "last",
                "hit_pm1_delta": 0.4,
                "all_positions_hit_pm1_delta": 0.5,
                "mae_improvement": 1.0,
                "rmse_improvement": 0.8,
            }
        ]
    )
    _write_table(ranking, root, "RANKING")
    _write_table(seed_summary, root, "SEED_SUMMARY")
    _write_table(per_seed, root, "PER_SEED_METRICS")
    _write_table(position, root, "POSITION_METRICS")
    _write_table(comparison, root, "BASELINE_COMPARISON")
    write_json(root / "SOURCE_PREDICTION_MAP.json", {"tasks": []})
    write_json(root / "BASELINE_METADATA.json", {"random_seed": 1})
    write_json(
        source_evidence / "manifest.json",
        {
            "status": "PASS",
            "stage": "prospective",
            "run_id": "source-prospective-1",
            "code_sha256": "code-v1",
            "data_sha256": "data-v1",
            "lineage_chain_sha256": "lineage-v1",
            "git_commit": "a" * 40,
        },
    )
    for name in (
        "campaign_config.json",
        "data_contract.json",
        "PREDICTION_LOCK.json",
        "VERIFICATION_SEAL.json",
    ):
        write_json(source_evidence / name, {"status": "PASS", "name": name})
    write_json(
        root / "ACTUALS_LOCK.json",
        {
            "status": "LOCKED",
            "scoring_id": "score-1",
            "prediction_lock_sha256": "prediction-lock-v1",
        },
    )
    write_json(
        root / "SCORING_REPORT.json",
        {
            "schema_version": "all-auto-prospective-scoring-v1",
            "status": "PASS",
            "scoring_id": "score-1",
            "created_at": "2026-08-05T09:00:00+00:00",
            "priority_metric": "hit_pm1",
            "source_run_id": "source-prospective-1",
            "prediction_lock_sha256": "prediction-lock-v1",
            "verification_seal_sha256": "seal-v1",
            "history_sha256": "history-v1",
            "actuals_sha256": "actuals-v1",
            "scoring_code_sha256": "scoring-code-v1",
            "champion": {
                "model_name": "AutoTFT",
                "track": "u_shared",
                "hit_pm1": 0.8,
                "all_positions_hit_pm1": 0.5,
                "mae": 1.0,
                "mse": 2.0,
                "rmse": 2.0**0.5,
                "worst_seed_hit_pm1": 0.8,
            },
        },
    )
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    write_json(
        root / "ARTIFACT_MANIFEST.json",
        {
            "status": "PASS",
            "scoring_id": "score-1",
            "files": files,
        },
    )
    write_sha256s(root)
    return root


def _backend_functions(calls: list[str]) -> RegistryBackendFunctions:
    def prepare(
        dsn: str,
        payload: dict[str, Any],
        frames: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        assert dsn == "postgresql://user:secret@db/loto"
        assert set(frames) == {
            "candidates",
            "seed_metrics",
            "position_metrics",
            "artifacts",
        }
        calls.append("prepare")
        return {
            "backend": "postgres",
            "status": "PASS",
            "phase": "PREPARED",
            "safe_uri": "postgresql://user:***@db/loto",
        }

    def mlflow(
        uri: str,
        experiment: str,
        payload: dict[str, Any],
        frames: dict[str, pd.DataFrame],
        **kwargs: Any,
    ) -> dict[str, Any]:
        assert uri == "http://mlflow.local"
        assert experiment == "prospective-test"
        assert kwargs["artifact_mode"] == "metadata"
        calls.append("mlflow")
        return {
            "backend": "mlflow",
            "status": "PASS",
            "safe_uri": uri,
            "parent_run_id": "mlflow-parent-1",
            "child_run_ids": ["child-1", "child-2"],
        }

    def finalize(
        dsn: str,
        payload: dict[str, Any],
        receipt: dict[str, Any],
    ) -> dict[str, Any]:
        assert receipt["parent_run_id"] == "mlflow-parent-1"
        calls.append("finalize")
        return {
            "backend": "postgres",
            "status": "PASS",
            "phase": "FINALIZED",
            "mlflow_parent_run_id": "mlflow-parent-1",
        }

    def blocked(
        dsn: str,
        payload: dict[str, Any],
        error: dict[str, Any],
    ) -> dict[str, Any]:
        calls.append("blocked")
        return {
            "backend": "postgres",
            "status": "PASS",
            "phase": "MARKED_BLOCKED",
        }

    return RegistryBackendFunctions(
        prepare_postgres=prepare,
        record_mlflow=mlflow,
        finalize_postgres=finalize,
        mark_postgres_blocked=blocked,
    )


def test_register_dual_backend_is_self_contained_and_source_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scoring = _scoring_artifact(tmp_path)
    before = _tree_hashes(scoring)
    calls: list[str] = []
    monkeypatch.setenv(
        "LOTO_POSTGRES_DSN",
        "postgresql://user:secret@db/loto",
    )
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry.verify_prospective_scoring",
        lambda _root: {"status": "PASS", "failures": []},
    )
    output = tmp_path / "registry-receipt"

    result = register_prospective_scoring(
        scoring_root=scoring,
        output=output,
        options=RegistryOptions(
            mlflow_uri="http://mlflow.local",
            mlflow_experiment="prospective-test",
        ),
        backends=_backend_functions(calls),
    )

    assert result["status"] == "PASS"
    assert calls == ["prepare", "mlflow", "finalize"]
    assert _tree_hashes(scoring) == before
    verified = verify_prospective_registry(output)
    assert verified["status"] == "PASS"
    assert verified["registration_status"] == "PASS"
    payload = json.loads((output / "REGISTRY_PAYLOAD.json").read_text(encoding="utf-8"))
    assert payload["metric_policy"]["priority_metric"] == "hit_pm1"
    assert payload["metric_policy"]["best_seed_only_selection"] is False
    assert payload["counts"]["candidate_count"] == 2
    assert payload["counts"]["seed_metric_rows"] == 2
    report_text = (output / "REGISTRY_REPORT.json").read_text(encoding="utf-8")
    assert "user:secret@" not in report_text
    assert "supersecret" not in report_text

    shutil.rmtree(scoring)
    relocated = verify_prospective_registry(output)
    assert relocated["status"] == "PASS"
    assert relocated["source_reverification"] == "NOT_AVAILABLE"


def test_mlflow_failure_marks_postgres_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scoring = _scoring_artifact(tmp_path)
    calls: list[str] = []
    monkeypatch.setenv(
        "LOTO_POSTGRES_DSN",
        "postgresql://user:secret@db/loto",
    )
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry.verify_prospective_scoring",
        lambda _root: {"status": "PASS", "failures": []},
    )
    base = _backend_functions(calls)

    def failing_mlflow(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append("mlflow")
        raise RuntimeError("cannot reach http://token:supersecret@mlflow.local")

    backends = RegistryBackendFunctions(
        prepare_postgres=base.prepare_postgres,
        record_mlflow=failing_mlflow,
        finalize_postgres=base.finalize_postgres,
        mark_postgres_blocked=base.mark_postgres_blocked,
    )
    output = tmp_path / "blocked-receipt"

    result = register_prospective_scoring(
        scoring_root=scoring,
        output=output,
        options=RegistryOptions(
            mlflow_uri="http://token:supersecret@mlflow.local",
            mlflow_experiment="prospective-test",
        ),
        backends=backends,
    )

    assert result["status"] == "BLOCKED"
    assert calls == ["prepare", "mlflow", "blocked"]
    verified = verify_prospective_registry(output)
    assert verified["status"] == "PASS"
    assert verified["registration_status"] == "BLOCKED"
    text = (output / "REGISTRY_REPORT.json").read_text(encoding="utf-8")
    assert "supersecret" not in text
    assert "secret@db" not in text


def test_missing_postgres_dsn_blocks_before_backend_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scoring = _scoring_artifact(tmp_path)
    calls: list[str] = []
    monkeypatch.delenv("LOTO_POSTGRES_DSN", raising=False)
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry.verify_prospective_scoring",
        lambda _root: {"status": "PASS", "failures": []},
    )

    result = register_prospective_scoring(
        scoring_root=scoring,
        output=tmp_path / "missing-dsn",
        options=RegistryOptions(
            mlflow_uri="http://mlflow.local",
            mlflow_experiment="prospective-test",
        ),
        backends=_backend_functions(calls),
    )

    assert result["status"] == "BLOCKED"
    assert calls == []


def test_registry_receipt_mutation_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scoring = _scoring_artifact(tmp_path)
    monkeypatch.setenv(
        "LOTO_POSTGRES_DSN",
        "postgresql://user:secret@db/loto",
    )
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry.verify_prospective_scoring",
        lambda _root: {"status": "PASS", "failures": []},
    )
    output = tmp_path / "registry-receipt"
    register_prospective_scoring(
        scoring_root=scoring,
        output=output,
        options=RegistryOptions(
            mlflow_uri="http://mlflow.local",
            mlflow_experiment="prospective-test",
        ),
        backends=_backend_functions([]),
    )
    (output / "REGISTRY_PAYLOAD.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    verified = verify_prospective_registry(output)

    assert verified["status"] == "FAIL"
    assert any("SHA256SUMS" in item for item in verified["failures"])


def test_position_registry_key_distinguishes_configs() -> None:
    shared = {
        "source_type": "model",
        "model_name": "AutoTFT",
        "baseline_name": None,
        "track": "u_shared",
        "seed": 1,
        "backend": "ray",
        "position": None,
        "variant": "reconciled",
        "unique_id": "P1",
        "hit_pm1": 1.0,
        "exact_hit": 1.0,
        "mae": 0.0,
        "mse": 0.0,
        "rmse": 0.0,
    }
    frame = pd.DataFrame(
        [
            {
                **shared,
                "candidate_id": "task:config-0",
                "config_index": 0,
            },
            {
                **shared,
                "candidate_id": "task:config-1",
                "config_index": 1,
            },
        ]
    )

    result = _position_metric_frame(frame, "registry-1")

    assert len(result) == 2
    assert result["row_key"].nunique() == 2


def test_registry_identity_is_stable_for_same_verified_scoring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scoring = _scoring_artifact(tmp_path)
    monkeypatch.setenv(
        "LOTO_POSTGRES_DSN",
        "postgresql://user:secret@db/loto",
    )
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry.verify_prospective_scoring",
        lambda _root: {"status": "PASS", "failures": []},
    )

    first = register_prospective_scoring(
        scoring_root=scoring,
        output=tmp_path / "receipt-one",
        options=RegistryOptions(
            mlflow_uri="http://mlflow.local",
            mlflow_experiment="prospective-test",
        ),
        backends=_backend_functions([]),
    )
    second = register_prospective_scoring(
        scoring_root=scoring,
        output=tmp_path / "receipt-two",
        options=RegistryOptions(
            mlflow_uri="http://mlflow.local",
            mlflow_experiment="prospective-test",
        ),
        backends=_backend_functions([]),
    )

    assert first["registry_id"] == second["registry_id"]
    assert first["payload_sha256"] == second["payload_sha256"]


def test_registry_requires_both_formal_backends() -> None:
    with pytest.raises(ValueError, match="requires both PostgreSQL and MLflow"):
        RegistryOptions(require_mlflow=False)
    with pytest.raises(ValueError, match="requires both PostgreSQL and MLflow"):
        RegistryOptions(require_postgres=False)


def test_registry_output_inside_source_is_rejected_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scoring = _scoring_artifact(tmp_path)
    monkeypatch.setattr(
        "loto.auto_campaign.prospective_registry.verify_prospective_scoring",
        lambda _root: {"status": "PASS", "failures": []},
    )
    nested = scoring / "new-output" / "registry"

    with pytest.raises(ValueError, match="outside the scoring artifact"):
        register_prospective_scoring(
            scoring_root=scoring,
            output=nested,
            options=RegistryOptions(mlflow_uri="http://mlflow.local"),
            backends=_backend_functions([]),
        )

    assert not nested.parent.exists()


def test_safe_error_redacts_uri_password_and_token_values() -> None:
    result = _safe_error(
        RuntimeError("authentication failed for hunter2 and token abc123"),
        secrets=(
            "postgresql://user:hunter2@db/loto",
            "http://mlflow.local?token=abc123",
        ),
        phase="BACKEND",
    )

    assert "hunter2" not in result["error"]
    assert "abc123" not in result["error"]
    assert result["error"].count("<redacted>") == 2
