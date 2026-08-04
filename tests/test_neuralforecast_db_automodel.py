from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

import pandas as pd

from loto.models.neuralforecast_adapter import AutoModelRequest, resolve_auto_model_plan
from loto.neuralforecast.db_automodel import (
    AutoModelCampaignConfig,
    DatabaseTableSource,
    build_campaign_plan,
    list_automodel_specs,
    load_database_table,
    prepare_panel,
    run_automodel_campaign,
)


def _numbers4_frame(rows: int = 40) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": range(1, rows + 1),
            "d1": [index % 10 for index in range(rows)],
            "d2": [(index + 1) % 10 for index in range(rows)],
            "d3": [(index + 2) % 10 for index in range(rows)],
            "d4": [(index + 3) % 10 for index in range(rows)],
        }
    )


def _write_sqlite(path: Path, frame: pd.DataFrame) -> None:
    with sqlite3.connect(path) as connection:
        frame.to_sql("normalized_draws", connection, index=False, if_exists="replace")


def test_load_sqlite_table_and_prepare_numbers4_panel(tmp_path):
    db_path = tmp_path / "datasets.sqlite3"
    _write_sqlite(db_path, _numbers4_frame(30))
    source = DatabaseTableSource(str(db_path), order_by="draw_no")
    loaded = load_database_table(source)
    panel = prepare_panel(loaded, game="numbers4", time_col="draw_no")
    assert panel.shape == (120, 3)
    assert panel["unique_id"].nunique() == 4
    assert panel.groupby("unique_id").size().nunique() == 1
    assert panel["y"].between(0, 9).all()


def test_all_catalog_automodels_are_in_campaign_plan(tmp_path):
    panel = prepare_panel(_numbers4_frame(), game="numbers4", time_col="draw_no")
    config = AutoModelCampaignConfig(
        source=DatabaseTableSource(str(tmp_path / "unused.sqlite3")),
        output_dir=str(tmp_path / "out"),
        dry_run=True,
    )
    plan = build_campaign_plan(config, panel)
    assert len(plan["models"]) == 36
    assert {row["class_name"] for row in plan["models"]} == {
        spec.class_name for spec in list_automodel_specs()
    }
    hint = next(row for row in plan["models"] if row["class_name"] == "AutoHINT")
    assert hint["special_handling"] == "hierarchical-ray-backend-override"
    multivariate = next(row for row in plan["models"] if row["class_name"] == "AutoTSMixer")
    assert multivariate["requires_n_series"] is True


def test_dry_run_loads_database_and_writes_auditable_plan(tmp_path):
    db_path = tmp_path / "datasets.sqlite3"
    _write_sqlite(db_path, _numbers4_frame())
    output = tmp_path / "campaign"
    result = run_automodel_campaign(
        AutoModelCampaignConfig(
            source=DatabaseTableSource(str(db_path)),
            output_dir=str(output),
            dry_run=True,
            workers=8,
            gpus=1,
            max_gpu_jobs=1,
        )
    )
    assert result["status"] == "DRY_RUN_VERIFIED"
    assert result["model_count"] == 36
    plan = json.loads((output / "campaign_plan.json").read_text(encoding="utf-8"))
    assert plan["panel"]["series"] == 4
    assert plan["optimization"]["requested_workers"] == 8
    assert plan["optimization"]["effective_workers"] == 1
    assert plan["optimization"]["queue_policy"] == "gpu_bounded_queue"


def test_single_automodel_passes_core_and_fit_arguments(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeNeuralForecast:
        def __init__(
            self,
            models,
            freq,
            local_scaler_type=None,
            local_static_scaler_type=None,
        ):
            captured["core"] = {
                "models": models,
                "freq": freq,
                "local_scaler_type": local_scaler_type,
                "local_static_scaler_type": local_static_scaler_type,
            }

        def fit(self, **kwargs):
            captured["fit"] = kwargs
            return self

        def predict(self, **kwargs):
            captured["predict"] = kwargs
            ids = sorted(captured["fit"]["df"]["unique_id"].unique())
            return pd.DataFrame(
                {
                    "unique_id": ids,
                    "ds": [41] * len(ids),
                    "AutoDLinear-optuna": [1.2, 2.4, 3.6, 8.8],
                }
            )

        def save(self, *args, **kwargs):
            captured["save"] = {"args": args, "kwargs": kwargs}

    monkeypatch.setitem(
        sys.modules,
        "neuralforecast",
        types.SimpleNamespace(NeuralForecast=FakeNeuralForecast),
    )
    monkeypatch.setattr(
        "loto.neuralforecast.db_automodel.construct_auto_model",
        lambda plan: types.SimpleNamespace(alias=plan.constructor_kwargs["alias"]),
    )

    db_path = tmp_path / "datasets.sqlite3"
    _write_sqlite(db_path, _numbers4_frame())
    result = run_automodel_campaign(
        AutoModelCampaignConfig(
            source=DatabaseTableSource(str(db_path)),
            output_dir=str(tmp_path / "campaign"),
            models=("nf-auto-dlinear",),
            val_size=4,
            num_samples=1,
            cpus=2,
            gpus=0,
            local_scaler_type="robust",
            local_static_scaler_type="standard",
            use_init_models=True,
        )
    )
    assert result["status"] == "SUCCEEDED"
    assert captured["core"]["freq"] == 1
    assert captured["core"]["local_scaler_type"] == "robust"
    assert captured["core"]["local_static_scaler_type"] == "standard"
    assert captured["fit"]["val_size"] == 4
    assert captured["fit"]["use_init_models"] is True
    assert captured["fit"]["id_col"] == "unique_id"
    assert captured["fit"]["time_col"] == "ds"
    assert captured["fit"]["target_col"] == "y"
    predictions = pd.read_csv(
        tmp_path / "campaign" / "models" / "nf-auto-dlinear" / "predictions.csv"
    )
    assert predictions["decoded_prediction"].tolist() == [1, 2, 4, 9]


def test_official_320_resources_use_ray_options_not_removed_legacy_arguments():
    ray_plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoDLinear",
            h=1,
            backend="ray",
            cpus=3,
            gpus=1,
            num_samples=2,
            time_budget=60,
            verbose=False,
        )
    )
    assert "cpus" not in ray_plan.constructor_kwargs
    assert "gpus" not in ray_plan.constructor_kwargs
    assert ray_plan.ray_options == {"cpus": 3, "gpus": 1}
    assert ray_plan.constructor_kwargs["time_budget"] == 60
    assert ray_plan.constructor_kwargs["verbose"] is False

    optuna_plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoDLinear",
            h=1,
            backend="optuna",
            cpus=3,
            gpus=1,
            parallel_trials=4,
        )
    )
    assert optuna_plan.ray_options is None
    assert optuna_plan.optuna_options == {"study_kwargs": {"n_jobs": 4}}
