from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression

from loto.evaluation.unified_campaign import UnifiedCampaignConfig, run_unified_campaign
from loto.models.catalog import ModelSpec
from loto.models.factory import RuntimeModel

MODEL_ID = "isotonic-calibrated-logistic"


def _spec() -> ModelSpec:
    return ModelSpec(
        model_id=MODEL_ID,
        family="calibrated",
        library="sklearn",
        task="candidate",
        class_name="CalibratedClassifierCV",
        package="sklearn",
        capabilities=("probability", "calibration"),
        default_params={"method": "isotonic", "cv": 3},
    )


def _numbers3_frame(rows: int = 40, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    values = rng.integers(0, 10, size=(rows, 3))
    return pd.DataFrame(
        {
            "draw_no": np.arange(1, rows + 1),
            "n1": values[:, 0],
            "n2": values[:, 1],
            "n3": values[:, 2],
        }
    )


def test_isotonic_runtime_wraps_deterministic_logistic() -> None:
    estimator = RuntimeModel(_spec(), seed=7)._construct_estimator()

    assert isinstance(estimator, CalibratedClassifierCV)
    assert estimator.method == "isotonic"
    assert estimator.cv == 3
    assert isinstance(estimator.estimator, LogisticRegression)
    assert estimator.estimator.C == 1.0
    assert estimator.estimator.max_iter == 1000
    assert estimator.estimator.random_state == 7


def test_isotonic_candidate_route_reaches_prediction_lock(tmp_path) -> None:
    output = tmp_path / "campaign"
    config = UnifiedCampaignConfig(
        output_dir=output,
        git_commit="0" * 40,
        games=("numbers3",),
        model_ids=(MODEL_ID,),
        seeds=(1,),
        folds=1,
        test_size=2,
        min_train_size=20,
        holdout_size=4,
        device="cpu",
    )

    summary = run_unified_campaign({"numbers3": _numbers3_frame()}, config)

    assert summary["matrix_complete"] is True
    assert summary["status"] == "SUCCEEDED"
    assert summary["status_counts"] == {"SUCCEEDED": 1}
    assert summary["holdout_evaluated"] is False
    assert summary["prospective_evaluated"] is False

    row = next(
        item
        for item in summary["results"]
        if item["source"] == "catalog" and item["candidate_id"] == MODEL_ID
    )
    assert row["status"] == "SUCCEEDED"
    assert row["reason"] == ""

    lock_path = output / "prediction_locks" / "numbers3" / MODEL_ID / "seed-1.json"
    assert lock_path.is_file()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["actuals_known"] is False
    assert payload["candidate_id"] == MODEL_ID
    assert payload["predictions"]
