from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.game.geometry import GameGeometry
from loto.probabilistic.contracts import ProbabilisticRunConfig
from loto.probabilistic.dataset import DatasetBundle
from loto.probabilistic.experiment_tracking import (
    ExperimentPersistenceError,
    ExperimentTrackingConfig,
    dataset_hash,
    evaluate_and_persist_conditional_bernoulli,
    issue_run_id,
    persist_experiment_tracking,
)
from loto.probabilistic.math.elementary_symmetric import sample_conditional_bernoulli
from loto.probabilistic.subset_evaluation import evaluate_conditional_bernoulli


def _bundle(*, rows: int = 26, seed: int = 17) -> DatasetBundle:
    geometry = GameGeometry(
        key="toy-select",
        family="select",
        positions=3,
        value_min=1,
        value_max=8,
    )
    rng = np.random.default_rng(seed)
    logits = np.linspace(-0.9, 0.9, geometry.universe_size)
    indicator = np.zeros((rows, geometry.universe_size), dtype=np.int8)
    values = np.zeros((rows, geometry.positions), dtype=np.int64)
    for row in range(rows):
        chosen = sample_conditional_bernoulli(logits, geometry.positions, rng=rng)
        indicator[row, list(chosen)] = 1
        values[row] = np.asarray(chosen, dtype=int) + geometry.value_min
    frame = pd.DataFrame(values, columns=geometry.column_names())
    frame.insert(0, "draw_no", np.arange(1, rows + 1))
    return DatasetBundle(
        game=geometry.key,
        geometry=geometry,
        frame=frame,
        values=values,
        draw_ids=tuple(str(index + 1) for index in range(rows)),
        data_version=f"toy-{rows}-{seed}",
        feature_set_hash="toy-feature-hash",
        candidate_indicator=indicator,
        set_members=tuple(tuple(int(value) for value in row) for row in values),
        set_cardinality=geometry.positions,
    )


def _config(**updates: object) -> ProbabilisticRunConfig:
    payload: dict[str, object] = {
        "models": ["pp-conditional-bernoulli-fixed-k"],
        "games": ["loto7"],
        "seeds": [23],
        "folds": 1,
        "test_size": 1,
        "min_train_size": 20,
        "posterior_draws": 32,
        "native_draws": 32,
        "native_max_train_rows": 100,
        "subset_prior_scale": 4.0,
        "subset_max_iter": 500,
        "subset_require_convergence": False,
        "subset_research_gain_min": 1.0,
    }
    payload.update(updates)
    return ProbabilisticRunConfig.model_validate(payload)


def _evaluated(tmp_path: Path):
    bundle = _bundle()
    config = _config()
    result = evaluate_conditional_bernoulli(
        bundle,
        config,
        output_dir=tmp_path,
        fixed_at="2026-08-03T12:00:00+00:00",
    )
    return bundle, config, result


def test_dataset_hash_and_run_id_are_deterministic() -> None:
    bundle = _bundle()
    first = dataset_hash(bundle)
    second = dataset_hash(bundle)
    assert first == second
    assert len(first) == 64
    run_id = issue_run_id(
        model_id="pp-conditional-bernoulli-fixed-k",
        created_at="2026-08-03T12:00:00+00:00",
        config_hash_value="a" * 64,
        data_hash_value=first,
    )
    assert run_id == issue_run_id(
        model_id="pp-conditional-bernoulli-fixed-k",
        created_at="2026-08-03T12:00:00+00:00",
        config_hash_value="a" * 64,
        data_hash_value=first,
    )
    assert run_id.startswith("ppl02-20260803-120000-")


def test_required_missing_postgres_dsn_fails_closed_and_records_report(tmp_path: Path) -> None:
    bundle, config, result = _evaluated(tmp_path)
    tracking = ExperimentTrackingConfig(
        enabled=True,
        required_backends=["postgres"],
        fail_closed=True,
        postgres_dsn_env="PPL02_TEST_DSN_THAT_DOES_NOT_EXIST",
    )
    with pytest.raises(ExperimentPersistenceError) as captured:
        persist_experiment_tracking(
            result,
            bundle,
            config,
            tracking,
            created_at="2026-08-03T12:10:00+00:00",
            repo_root=tmp_path,
        )
    report = captured.value.report
    assert report.status == "BLOCKED"
    assert report.backends[0].backend == "postgres"
    assert report.backends[0].required is True
    assert report.backends[0].status == "BLOCKED"
    recorded = json.loads(
        (tmp_path / "tracking/persistence_report.json").read_text(encoding="utf-8")
    )
    assert recorded["status"] == "BLOCKED"
    assert (tmp_path / "tracking/run_record.json").exists()


def test_optional_mlflow_failure_is_partial_not_false_success(tmp_path: Path) -> None:
    bundle, config, result = _evaluated(tmp_path)
    tracking = ExperimentTrackingConfig(
        enabled=True,
        required_backends=[],
        optional_backends=["mlflow"],
        mlflow_uri=None,
        fail_closed=True,
    )
    report = persist_experiment_tracking(
        result,
        bundle,
        config,
        tracking,
        created_at="2026-08-03T12:20:00+00:00",
        repo_root=tmp_path,
    )
    assert report.status == "PARTIAL"
    assert report.backends[0].status == "BLOCKED"
    assert report.backends[0].required is False
    assert report.prediction_payload_sha256 == result.prospective_prediction["payload_sha256"]
    assert report.device["pid"] > 0
    assert report.git_commit == os.getenv("GITHUB_SHA", "UNAVAILABLE")


@pytest.mark.skipif(
    importlib.util.find_spec("pyarrow") is None,
    reason="pyarrow is required for the Parquet backend",
)
def test_parquet_backend_writes_normalized_tables_and_refreshes_manifest(tmp_path: Path) -> None:
    bundle, config, result = _evaluated(tmp_path)
    report = persist_experiment_tracking(
        result,
        bundle,
        config,
        ExperimentTrackingConfig(enabled=True, required_backends=["parquet"]),
        created_at="2026-08-03T12:30:00+00:00",
        repo_root=tmp_path,
    )
    assert report.status == "PASS"
    root = tmp_path / "tracking/parquet"
    runs = pd.read_parquet(root / "runs.parquet")
    metrics = pd.read_parquet(root / "metrics.parquet")
    predictions = pd.read_parquet(root / "predictions.parquet")
    artifacts = pd.read_parquet(root / "artifacts.parquet")
    assert len(runs) == 1
    assert runs.loc[0, "run_id"] == report.run_id
    assert {"hit_at_1", "mae", "mse", "rmse"} <= set(metrics["metric_name"])
    prospective = predictions[predictions["row_kind"] == "prospective"].iloc[0]
    assert pd.isna(prospective["actual_json"])
    assert not artifacts.empty
    manifest = json.loads((tmp_path / "ARTIFACT_MANIFEST.json").read_text(encoding="utf-8"))
    paths = {item["path"] for item in manifest["files"]}
    assert "tracking/parquet/runs.parquet" in paths
    assert "tracking/persistence_report.json" in paths


@pytest.mark.skipif(
    importlib.util.find_spec("pyarrow") is None,
    reason="pyarrow is required for the Parquet backend",
)
def test_evaluate_and_persist_wrapper_keeps_prediction_actual_unknown(tmp_path: Path) -> None:
    result, report = evaluate_and_persist_conditional_bernoulli(
        _bundle(),
        _config(run_id="ppl02-explicit-test-run"),
        ExperimentTrackingConfig(enabled=True, required_backends=["parquet"]),
        output_dir=tmp_path,
        fixed_at="2026-08-03T12:00:00+00:00",
        created_at="2026-08-03T12:40:00+00:00",
        repo_root=tmp_path,
    )
    assert report.run_id == "ppl02-explicit-test-run"
    assert result.prospective_prediction["payload"]["actual_known"] is False
    run_record = json.loads((tmp_path / "tracking/run_record.json").read_text(encoding="utf-8"))
    assert run_record["actual_known"] is False
    assert run_record["prediction_payload_sha256"] == report.prediction_payload_sha256


def test_tracking_config_rejects_backend_overlap() -> None:
    with pytest.raises(ValueError, match="both required and optional"):
        ExperimentTrackingConfig(
            enabled=True,
            required_backends=["parquet"],
            optional_backends=["parquet"],
        )
