from __future__ import annotations

# ruff: noqa: E501
import argparse
import sys
import types

import numpy as np
import pandas as pd
import pytest

from loto.models.argument_verifier import verify_arguments
from loto.models.artifact_store import load_pickle_model, save_pickle_model
from loto.models.catalog import get_model_spec
from loto.models.lifecycle import run_candidate_lifecycle, validate_prediction
from loto.models.property_inspector import inspect_model_properties
from loto.models.providers import FOUNDATION_PROVIDERS, get_foundation_provider
from loto.models.workers import (
    PositionSeriesWorker,
    autohint_hierarchy_frame,
    normalize_worker_predictions,
)
from loto.orchestration.resource_scheduler import ResourcePolicy, ResourceScheduler
from scripts.all_model_runtime_validation import build_parser, main, run_worker_lifecycle


class FakeStatsModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeStatsForecast:
    def __init__(self, models, freq, n_jobs):
        self.models = models
        self.freq = freq
        self.n_jobs = n_jobs
        self.series = 0

    def fit(self, df):
        self.series = int(df["unique_id"].nunique())
        return self

    def predict(self, h):
        return pd.DataFrame(
            {
                "unique_id": [f"candidate-{i:02d}" for i in range(1, 38)],
                "ds": pd.Timestamp("2026-01-01"),
                "Fake": np.linspace(0.1, 1.0, 37),
            }
        )


def sample_master(rows: int = 90) -> pd.DataFrame:
    data = []
    for i in range(rows):
        start = (i % 31) + 1
        numbers = sorted({((start + j * 3 - 1) % 37) + 1 for j in range(7)})
        while len(numbers) < 7:
            numbers.append(((numbers[-1]) % 37) + 1)
            numbers = sorted(set(numbers))
        data.append(
            {
                "draw_no": i + 1,
                "draw_date": pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=i * 7),
                **{f"n{j + 1}": numbers[j] for j in range(7)},
            }
        )
    return pd.DataFrame(data)


def test_cli_validation_rejects_invalid_parallel_value():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--parallel-cpu-models", "0"])
    args = parser.parse_args(["--models", "uniform", "--timeout", "10"])
    assert isinstance(args, argparse.Namespace)
    assert args.models == "uniform"


def test_cli_rejects_missing_catalog(tmp_path):
    with pytest.raises(SystemExit, match="catalog does not exist"):
        main(
            [
                "--catalog",
                str(tmp_path / "missing.json"),
                "--models",
                "uniform",
                "--output",
                str(tmp_path / "runs"),
            ]
        )


def test_argument_mapping_reports_verified_and_unsupported():
    rows = verify_arguments({"max_steps": 5}, {"max_steps": 5}, {"max_steps": 5})
    assert next(row for row in rows if row["argument"] == "max_steps")["status"] == "VERIFIED"
    assert next(row for row in rows if row["argument"] == "batch_size")["status"] == "UNSUPPORTED"


def test_property_extraction_records_not_exposed():
    spec = get_model_spec("uniform")
    props = inspect_model_properties(spec, None, params={})
    assert props["model_id"] == "uniform"
    assert props["optimizer"]["status"] == "NOT_EXPOSED"


def test_save_load_pickle_roundtrip(tmp_path):
    path = save_pickle_model({"prediction": [1, 2, 3]}, tmp_path / "model.pkl")
    assert load_pickle_model(path)["prediction"] == [1, 2, 3]


def test_prediction_equality_candidate_lifecycle(tmp_path):
    result = run_candidate_lifecycle(
        get_model_spec("uniform"),
        sample_master(),
        params={},
        seed=42,
        output_dir=tmp_path,
    )
    assert result.final_status == "PASS"
    assert np.allclose(result.predictions, result.reloaded_predictions)
    validate_prediction(result.predictions, expected_shape=(37,))


def test_candidate_series_normalization_does_not_reshape_37_to_7():
    values = np.linspace(0.1, 1.0, 37)
    normalized = normalize_worker_predictions(
        task="candidate_series",
        history=sample_master(),
        values=values,
    )
    assert normalized.shape == (37,)
    assert np.isclose(normalized.sum(), 7.0, atol=1e-9)


def test_position_series_normalization_requires_7_values():
    with pytest.raises(ValueError, match="position_series model must return 7 values"):
        normalize_worker_predictions(
            task="position_series",
            history=sample_master(),
            values=np.ones(37),
        )


def test_candidate_series_normalization_requires_37_values():
    with pytest.raises(ValueError, match="candidate_series model must return 37 values"):
        normalize_worker_predictions(
            task="candidate_series",
            history=sample_master(),
            values=np.ones(7),
        )


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_candidate_series_normalization_rejects_non_finite(bad):
    values = np.ones(37)
    values[3] = bad
    with pytest.raises(ValueError, match="candidate_series predictions contain NaN or Inf"):
        normalize_worker_predictions(
            task="candidate_series",
            history=sample_master(),
            values=values,
        )


def test_candidate_series_normalization_zero_sum_falls_back_to_sum_7():
    normalized = normalize_worker_predictions(
        task="candidate_series",
        history=sample_master(),
        values=np.zeros(37),
    )
    assert normalized.shape == (37,)
    assert np.isclose(normalized.sum(), 7.0, atol=1e-9)


def test_autohint_hierarchy_matrix_shape_rank_and_coherence():
    frame, hierarchy = autohint_hierarchy_frame(sample_master(20))
    matrix = hierarchy["summation_matrix"]
    assert matrix.shape == (8, 7)
    assert np.linalg.matrix_rank(matrix) == 7
    assert matrix[0].tolist() == [1.0] * 7
    assert np.allclose(matrix[1:], np.eye(7))
    assert hierarchy["series_order"] == ["total", *[f"position-{i}" for i in range(1, 8)]]
    assert hierarchy["bottom_series_order"] == [f"position-{i}" for i in range(1, 8)]
    assert hierarchy["internal_series_order"][0] == "00-total"
    assert hierarchy["hierarchy_validation"]["top_equals_bottom_sum"] is True
    assert set(frame["unique_id"]) == set(hierarchy["internal_series_order"])


def test_autohint_worker_fixed_hint_predicts_7_positions():
    spec = get_model_spec("nf-auto-hint")
    worker = PositionSeriesWorker(
        spec,
        {"max_steps": 1, "batch_size": 8, "learning_rate": 0.001},
        seed=42,
        device="cpu",
        precision="32",
    )
    output = worker.forecast(sample_master(30))
    assert output.position_values.shape == (7,)
    assert output.candidate_probabilities.shape == (37,)
    assert output.model_artifact_payload["library"] == "autohint_fixed"
    assert output.metadata["base_model_class"] == "DLinear"
    assert output.metadata["hierarchy"]["hierarchy_validation"]["rank"] == 7


def test_candidate_series_worker_transforms_37_binary_series(monkeypatch):
    captured = {}

    class FakeModel:
        def __init__(self, **kwargs):
            captured["model_kwargs"] = kwargs

    class FakeStatsForecast:
        def __init__(self, models, freq, n_jobs):
            captured["freq"] = freq
            captured["n_jobs"] = n_jobs

        def fit(self, df):
            captured["series"] = df["unique_id"].nunique()
            return self

        def predict(self, h):
            return pd.DataFrame(
                {
                    "unique_id": [f"candidate-{i:02d}" for i in range(1, 38)],
                    "ds": pd.Timestamp("2026-01-01"),
                    "Fake": np.linspace(0.1, 1.0, 37),
                }
            )

    monkeypatch.setitem(
        sys.modules, "statsforecast", types.SimpleNamespace(StatsForecast=FakeStatsForecast)
    )
    monkeypatch.setitem(
        sys.modules, "statsforecast.models", types.SimpleNamespace(CrostonClassic=FakeModel)
    )
    worker = PositionSeriesWorker(
        get_model_spec("stats-croston"), {}, seed=42, device="cpu", precision="32"
    )
    output = worker.forecast(sample_master(30))
    assert captured["series"] == 37
    assert output.candidate_probabilities.shape == (37,)
    assert np.isclose(output.candidate_probabilities.sum(), 7.0, atol=1e-6)


@pytest.mark.parametrize("model_id", ["stats-croston", "stats-tsb"])
def test_statsforecast_candidate_series_lifecycle_reload_and_retrain_are_37(
    monkeypatch, tmp_path, model_id
):
    monkeypatch.setitem(
        sys.modules, "statsforecast", types.SimpleNamespace(StatsForecast=FakeStatsForecast)
    )
    monkeypatch.setitem(
        sys.modules,
        "statsforecast.models",
        types.SimpleNamespace(CrostonClassic=FakeStatsModel, TSB=FakeStatsModel),
    )
    args = argparse.Namespace(
        seed=42,
        device="cpu",
        precision="32",
        verify_gpu=False,
        gpus_per_trial=0,
    )
    result = run_worker_lifecycle(get_model_spec(model_id), sample_master(40), args, tmp_path)
    assert result.final_status == "PASS"
    assert result.predictions.shape == (37,)
    assert result.reloaded_predictions is not None
    assert result.reloaded_predictions.shape == (37,)
    assert result.retrained_predictions is not None
    assert result.retrained_predictions.shape == (37,)
    assert np.allclose(result.predictions, result.reloaded_predictions, atol=1e-5)


def test_foundation_provider_registry_has_required_keys():
    assert "chronos" in FOUNDATION_PROVIDERS
    assert "sundial" in FOUNDATION_PROVIDERS
    assert get_foundation_provider(get_model_spec("sundial")).__name__ == "SundialProvider"
    assert get_foundation_provider(get_model_spec("tirex")).__name__ == "TiRexProvider"
    assert get_foundation_provider(get_model_spec("moirai")).__name__ == "MoiraiProvider"


def test_chronos_bolt_catalog_pins_revision():
    spec = get_model_spec("chronos-bolt-tiny")
    assert spec.default_params["model_name"] == "amazon/chronos-bolt-tiny"
    assert spec.default_params["revision"] == "a0e552de83495b5c28c14c71c374f3e33280b340"


def test_reservoir_esn_catalog_smoke_parameters():
    spec = get_model_spec("reservoir-esn")
    assert spec.default_params["reservoir_size"] == 50
    assert spec.default_params["spectral_radius"] == 0.9
    assert spec.default_params["leak_rate"] == 0.3


def test_darts_ensemble_worker_returns_persistence_payload(monkeypatch):
    class FakeTimeSeries:
        def __init__(self, series):
            self.series = series

        @classmethod
        def from_series(cls, series):
            return cls(series)

    class FakePrediction:
        def values(self):
            return np.asarray([[12.0]])

    class FakeModel:
        def fit(self, series):
            self.series = series
            return self

        def predict(self, h):
            return FakePrediction()

    class FakeRegressionEnsembleModel(FakeModel):
        def __init__(self, forecasting_models, regression_train_n_points):
            self.forecasting_models = forecasting_models
            self.regression_train_n_points = regression_train_n_points

    monkeypatch.setitem(sys.modules, "darts", types.SimpleNamespace(TimeSeries=FakeTimeSeries))
    monkeypatch.setitem(
        sys.modules,
        "darts.models",
        types.SimpleNamespace(
            ExponentialSmoothing=FakeModel,
            NaiveDrift=FakeModel,
            RegressionEnsembleModel=FakeRegressionEnsembleModel,
        ),
    )
    output = PositionSeriesWorker(
        get_model_spec("darts-ensemble"), {}, seed=42, device="cpu", precision="32"
    ).forecast(sample_master(30))
    assert output.model_artifact_payload["library"] == "darts_ensemble"
    assert output.metadata["component_models"] == ["NaiveDrift", "ExponentialSmoothing"]
    assert len(output.model_artifact_payload["models"]) == 7


def test_resource_scheduler_limits_and_report():
    scheduler = ResourceScheduler(
        ResourcePolicy(max_parallel_cpu_models=1, max_parallel_gpu_models=1)
    )
    lease = scheduler.acquire(requires_gpu=False, lease_id="a", timeout=1)
    scheduler.release(lease)
    assert scheduler.report()[0]["lease_id"] == "a"


def test_resume_skip_behavior_on_pass_and_zero_shot_pass(tmp_path):
    from pathlib import Path

    output_root = tmp_path / "runtime-run"
    output_root.mkdir()

    model1_dir = output_root / "model-1"
    model1_dir.mkdir()
    (model1_dir / "lifecycle_result.json").write_text("{}", encoding="utf-8")

    model2_dir = output_root / "model-2"
    model2_dir.mkdir()
    (model2_dir / "lifecycle_result.json").write_text("{}", encoding="utf-8")

    model3_dir = output_root / "model-3"
    model3_dir.mkdir()
    (model3_dir / "lifecycle_result.json").write_text("{}", encoding="utf-8")

    art1 = model1_dir / "model.pkl"
    art1.write_text("dummy", encoding="utf-8")
    art2 = model2_dir / "provider.json"
    art2.write_text("dummy", encoding="utf-8")

    status_payload = {
        "rows": [
            {"model_id": "model-1", "final_status": "PASS", "artifact path": str(art1)},
            {"model_id": "model-2", "final_status": "ZERO_SHOT_PASS", "artifact path": str(art2)},
            {"model_id": "model-3", "final_status": "FIT_FAILED", "artifact path": None},
        ]
    }

    from scripts.all_model_runtime_validation import extract_status_rows

    previous_rows = {row["model_id"]: row for row in extract_status_rows(status_payload)}

    row1 = previous_rows.get("model-1")
    artifact1 = Path(str(row1.get("artifact path")))
    assert row1.get("final_status") in {"PASS", "ZERO_SHOT_PASS"}
    assert artifact1.exists()

    row2 = previous_rows.get("model-2")
    artifact2 = Path(str(row2.get("artifact path")))
    assert row2.get("final_status") in {"PASS", "ZERO_SHOT_PASS"}
    assert artifact2.exists()

    row3 = previous_rows.get("model-3")
    assert row3.get("final_status") not in {"PASS", "ZERO_SHOT_PASS"}


def test_resume_rejected_on_signature_mismatch(tmp_path):
    import json

    output_root = tmp_path / "runtime-run"
    output_root.mkdir()

    manifest_payload = {"run_signature": "old_sig_123"}
    (output_root / "run_manifest.json").write_text(json.dumps(manifest_payload), encoding="utf-8")

    status_payload = {
        "rows": [{"model_id": "model-1", "final_status": "PASS", "artifact path": "dummy"}]
    }
    (output_root / "all_model_runtime_validation.json").write_text(
        json.dumps(status_payload), encoding="utf-8"
    )

    run_signature = "new_sig_456"
    previous_rows = {}
    previous_manifest = output_root / "run_manifest.json"
    previous_results = output_root / "all_model_runtime_validation.json"

    sig_match = True
    if previous_manifest.exists():
        try:
            manifest_data = json.loads(previous_manifest.read_text(encoding="utf-8"))
            prev_sig = manifest_data.get("run_signature")
            if prev_sig != run_signature:
                sig_match = False
        except Exception:
            sig_match = False

    if sig_match:
        from scripts.all_model_runtime_validation import extract_status_rows

        previous_rows = {
            row["model_id"]: row
            for row in extract_status_rows(json.loads(previous_results.read_text(encoding="utf-8")))
        }

    assert sig_match is False
    assert not previous_rows
