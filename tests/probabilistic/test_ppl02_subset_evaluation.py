from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from loto.game.geometry import GameGeometry
from loto.probabilistic.contracts import ProbabilisticRunConfig
from loto.probabilistic.dataset import DatasetBundle
from loto.probabilistic.math.elementary_symmetric import sample_conditional_bernoulli
from loto.probabilistic.statuses import TrialStatus
from loto.probabilistic.subset_evaluation import (
    BASELINES,
    evaluate_conditional_bernoulli,
    evaluate_cutoff,
    fix_prospective_prediction,
    verify_fixed_prediction,
)


def _bundle(*, rows: int = 42, seed: int = 7) -> DatasetBundle:
    geometry = GameGeometry(
        key="toy-select",
        family="select",
        positions=3,
        value_min=1,
        value_max=8,
    )
    logits = np.linspace(-1.1, 1.1, geometry.universe_size)
    rng = np.random.default_rng(seed)
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
        "seeds": [11, 13],
        "folds": 1,
        "test_size": 2,
        "min_train_size": 20,
        "posterior_draws": 32,
        "native_draws": 32,
        "native_max_train_rows": 100,
        "subset_prior_scale": 4.0,
        "subset_max_iter": 500,
        "subset_require_convergence": False,
        "subset_research_gain_min": 1.0,
        "subset_ece_bins": 8,
    }
    payload.update(updates)
    return ProbabilisticRunConfig.model_validate(payload)


def test_evaluation_reports_priority_metrics_and_all_baselines() -> None:
    result = evaluate_conditional_bernoulli(
        _bundle(),
        _config(),
        fixed_at="2026-08-03T12:00:00+00:00",
    )
    assert result.status == TrialStatus.RESEARCH_NO_GAIN.value
    assert len(result.model_rows) == 4
    assert len(result.baseline_rows) == 4 * len(BASELINES)
    assert set(result.baseline_summary) == set(BASELINES)
    metrics = result.model_rows[0]
    required = {
        "hit_at_1",
        "all_positions_hit_at_1",
        "mae",
        "mse",
        "rmse",
        "candidate_brier",
        "candidate_ece",
        "candidate_log_loss",
        "expected_overlap",
        "joint_log_probability",
        "joint_log_loss",
    }
    assert required <= metrics.keys()
    for position in range(1, 4):
        assert f"position_{position}_hit_at_1" in metrics
        assert f"position_{position}_mae" in metrics
        assert f"position_{position}_mse" in metrics
    assert result.promotion["promotable"] is False
    assert result.promotion["best_baseline"] in BASELINES


def test_multiseed_summary_has_mean_variance_and_worst() -> None:
    result = evaluate_conditional_bernoulli(_bundle(), _config())
    summary = result.model_summary
    assert set(summary["by_seed"]) == {"11", "13"}
    hit = summary["metrics"]["hit_at_1"]
    assert set(hit) == {"mean", "variance", "std", "worst", "best"}
    assert 0.0 <= hit["worst"] <= hit["best"] <= 1.0
    loss = summary["metrics"]["joint_log_loss"]
    assert loss["worst"] >= loss["best"]


def test_cutoff_isolation_ignores_rows_after_scored_actual() -> None:
    bundle = _bundle(rows=44)
    cutoff = 40
    first, _ = evaluate_cutoff(bundle, _config(seeds=[17]), cutoff=cutoff, seed=17)
    changed_values = bundle.values.copy()
    changed_indicator = bundle.candidate_indicator.copy()
    changed_values[cutoff + 1 :] = np.flip(changed_values[cutoff + 1 :], axis=1)
    changed_indicator[cutoff + 1 :] = np.roll(changed_indicator[cutoff + 1 :], 2, axis=1)
    altered = replace(
        bundle,
        values=changed_values,
        candidate_indicator=changed_indicator,
        data_version="tampered-future-only",
    )
    second, _ = evaluate_cutoff(altered, _config(seeds=[17]), cutoff=cutoff, seed=17)
    assert first["prediction"] == second["prediction"]
    assert np.allclose(first["candidate_marginals"], second["candidate_marginals"])
    assert first["joint_log_probability"] == second["joint_log_probability"]


def test_prospective_prediction_is_time_fixed_and_tamper_evident() -> None:
    fixed = fix_prospective_prediction(
        {
            "model_id": "pp-conditional-bernoulli-fixed-k",
            "prediction": [1, 3, 5],
            "actual_known": False,
        },
        fixed_at="2026-08-03T12:00:00+00:00",
    )
    assert fixed["fixed_at"] == "2026-08-03T12:00:00+00:00"
    assert verify_fixed_prediction(fixed)
    assert "actual" not in fixed["payload"]
    fixed["payload"]["prediction"][0] = 2
    assert not verify_fixed_prediction(fixed)


def test_artifacts_include_dual_manifest_and_verified_prediction(tmp_path: Path) -> None:
    result = evaluate_conditional_bernoulli(
        _bundle(),
        _config(seeds=[19], test_size=1),
        output_dir=tmp_path,
        fixed_at="2026-08-03T12:00:00+00:00",
    )
    assert Path(result.artifact_dir) == tmp_path.resolve()
    required = {
        "evaluation/model_folds.csv",
        "evaluation/baseline_folds.csv",
        "evaluation/model_summary.json",
        "evaluation/baseline_summary.json",
        "evaluation/promotion_decision.json",
        "prospective/prediction.fixed.json",
        "prospective/candidate_marginals.csv",
        "report/VERIFICATION_REPORT.json",
    }
    artifact_manifest = json.loads(
        (tmp_path / "ARTIFACT_MANIFEST.json").read_text(encoding="utf-8")
    )
    sha_manifest = json.loads((tmp_path / "SHA256SUMS.json").read_text(encoding="utf-8"))
    assert artifact_manifest == sha_manifest
    recorded = {row["path"]: row for row in artifact_manifest["files"]}
    assert required <= recorded.keys()
    for relative, row in recorded.items():
        path = tmp_path / relative
        assert path.stat().st_size == row["size"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    sealed = json.loads(
        (tmp_path / "prospective/prediction.fixed.json").read_text(encoding="utf-8")
    )
    assert verify_fixed_prediction(sealed)
    report = json.loads((tmp_path / "report/VERIFICATION_REPORT.json").read_text(encoding="utf-8"))
    assert report["future_actual_in_prediction_payload"] is False
    assert report["prediction_sha256_verified"] is True
    assert report["ppl01_model_ids_modified"] == 0
