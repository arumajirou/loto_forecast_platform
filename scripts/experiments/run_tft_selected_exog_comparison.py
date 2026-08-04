from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from neuralforecast import NeuralForecast
from neuralforecast.losses.pytorch import MAE
from neuralforecast.models import TFT
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = time.strftime("tft-selected-exog-%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / "experiments" / RUN_ID
OUT.mkdir(parents=True, exist_ok=False)

torch.set_float32_matmul_precision("high")

GAME = "loto7"
H = 1
INPUT_SIZE = 64
MAX_STEPS = 100
N_WINDOWS = 20
SEEDS = [42, 123, 2026]

ALL_FUTURE = [
    "feat_year",
    "feat_month",
    "feat_day",
    "feat_dayofweek",
    "feat_weekofyear",
    "feat_dayofyear",
    "feat_is_weekend",
    "feat_is_month_start",
    "feat_is_month_end",
    "feat_dow_sin",
    "feat_dow_cos",
    "feat_month_sin",
    "feat_month_cos",
]

ALL_HISTORICAL = [
    "hist_lag_1",
    "hist_lag_2",
    "hist_lag_3",
    "hist_lag_7",
    "hist_lag_14",
    "hist_lag_28",
    "hist_roll_mean_3",
    "hist_roll_mean_7",
    "hist_roll_mean_14",
    "hist_roll_mean_28",
    "hist_roll_std_7",
    "hist_roll_std_14",
    "hist_roll_std_28",
    "hist_ewm_mean_7",
    "hist_ewm_mean_14",
]

selection = yaml.safe_load((ROOT / "configs/tft_selected_exog.yaml").read_text(encoding="utf-8"))

SELECTED_FUTURE = selection.get(
    "future_exog",
    [],
)
SELECTED_HISTORICAL = selection.get(
    "historical_exog",
    [],
)

for column in SELECTED_FUTURE:
    if column not in ALL_FUTURE:
        raise ValueError(f"Unknown selected future feature: {column}")

for column in SELECTED_HISTORICAL:
    if column not in ALL_HISTORICAL:
        raise ValueError(f"Unknown selected historical feature: {column}")

CONDITIONS = {
    "no_exog": {
        "futr": [],
        "hist": [],
    },
    "all_exog": {
        "futr": ALL_FUTURE,
        "hist": ALL_HISTORICAL,
    },
    "selected_exog": {
        "futr": SELECTED_FUTURE,
        "hist": SELECTED_HISTORICAL,
    },
    "selected_future_only": {
        "futr": SELECTED_FUTURE,
        "hist": [],
    },
    "selected_historical_only": {
        "futr": [],
        "hist": SELECTED_HISTORICAL,
    },
}

all_columns = list(dict.fromkeys(ALL_FUTURE + ALL_HISTORICAL))

db_url = (
    f"postgresql+psycopg://{os.environ['DB_USER']}:"
    f"{os.environ['DB_PASSWORD']}@"
    f"{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/"
    f"{os.environ['DB_NAME']}"
)

engine = create_engine(db_url)

df = pd.read_sql(
    f"""
    SELECT
        unique_id,
        ds,
        y,
        {", ".join(all_columns)}
    FROM dataset.loto_y_ts_unified
    WHERE loto = '{GAME}'
      AND ts_type = 'raw'
    ORDER BY unique_id, ds
    """,
    engine,
)

df["actual_ds"] = pd.to_datetime(df["ds"])
df["draw_index"] = df.groupby("unique_id").cumcount()
df["ds"] = pd.Timestamp("2000-01-01") + pd.to_timedelta(
    df["draw_index"],
    unit="D",
)

df["y"] = pd.to_numeric(
    df["y"],
    errors="coerce",
)

for column in all_columns:
    df[column] = pd.to_numeric(
        df[column],
        errors="coerce",
    )

df = df.replace(
    [np.inf, -np.inf],
    np.nan,
)

# 全条件で同じ行を使うため、
# 最大特徴集合の欠損をまとめて除外する。
df = df.dropna(subset=["y", *all_columns]).reset_index(drop=True)

common_dates = sorted(set.intersection(*[set(group["ds"]) for _, group in df.groupby("unique_id")]))

test_dates = common_dates[-N_WINDOWS:]

results = []
predictions = []

for seed in SEEDS:
    for condition, exog in CONDITIONS.items():
        columns = list(
            dict.fromkeys(
                [
                    "unique_id",
                    "ds",
                    "y",
                    *exog["futr"],
                    *exog["hist"],
                ]
            )
        )

        model_df = df[columns].copy()

        fold_metrics = []

        for fold, test_date in enumerate(
            test_dates,
            start=1,
        ):
            train_df = model_df[model_df["ds"] < test_date].copy()

            test_df = model_df[model_df["ds"] == test_date].copy()

            model = TFT(
                h=H,
                input_size=INPUT_SIZE,
                max_steps=MAX_STEPS,
                learning_rate=1e-3,
                loss=MAE(),
                futr_exog_list=exog["futr"],
                hist_exog_list=exog["hist"],
                stat_exog_list=[],
                scaler_type="robust",
                batch_size=32,
                random_seed=seed,
                enable_progress_bar=False,
                logger=False,
            )

            nf = NeuralForecast(
                models=[model],
                freq="D",
            )

            start = time.perf_counter()
            nf.fit(df=train_df)
            elapsed = time.perf_counter() - start

            if exog["futr"]:
                futr_df = test_df[
                    [
                        "unique_id",
                        "ds",
                        *exog["futr"],
                    ]
                ].copy()

                forecast = nf.predict(futr_df=futr_df)
            else:
                forecast = nf.predict()

            pred_col = [
                column
                for column in forecast.columns
                if column
                not in {
                    "unique_id",
                    "ds",
                }
            ][0]

            merged = test_df[["unique_id", "ds", "y"]].merge(
                forecast[
                    [
                        "unique_id",
                        "ds",
                        pred_col,
                    ]
                ],
                on=["unique_id", "ds"],
                how="inner",
            )

            actual = merged["y"].to_numpy(dtype=float)
            predicted = merged[pred_col].to_numpy(dtype=float)

            errors = np.abs(actual - predicted)

            metrics = {
                "seed": seed,
                "condition": condition,
                "fold": fold,
                "test_date": str(test_date),
                "mae": float(np.mean(errors)),
                "mse": float(np.mean((actual - predicted) ** 2)),
                "within_1": float(np.mean(errors <= 1.0)),
                "training_seconds": elapsed,
            }

            fold_metrics.append(metrics)

            for index, row in merged.iterrows():
                predictions.append(
                    {
                        **metrics,
                        "unique_id": row["unique_id"],
                        "actual": float(row["y"]),
                        "prediction": float(row[pred_col]),
                        "absolute_error": float(abs(row["y"] - row[pred_col])),
                    }
                )

        fold_df = pd.DataFrame(fold_metrics)

        results.append(
            {
                "seed": seed,
                "condition": condition,
                "future_features": exog["futr"],
                "historical_features": exog["hist"],
                "n_future_features": len(exog["futr"]),
                "n_historical_features": len(exog["hist"]),
                "mean_mae": float(fold_df["mae"].mean()),
                "median_mae": float(fold_df["mae"].median()),
                "std_mae": float(fold_df["mae"].std()),
                "mean_mse": float(fold_df["mse"].mean()),
                "mean_within_1": float(fold_df["within_1"].mean()),
                "positive_fold_rate": None,
                "total_training_seconds": float(fold_df["training_seconds"].sum()),
            }
        )

results_df = pd.DataFrame(results)

baseline = results_df[results_df["condition"] == "no_exog"][["seed", "mean_mae"]].rename(
    columns={"mean_mae": "baseline_mae"}
)

results_df = results_df.merge(
    baseline,
    on="seed",
    how="left",
)

results_df["mae_improvement_percent_vs_no_exog"] = (
    (results_df["baseline_mae"] - results_df["mean_mae"]) / results_df["baseline_mae"] * 100.0
)

prediction_df = pd.DataFrame(predictions)

for index, row in results_df.iterrows():
    if row["condition"] == "no_exog":
        results_df.loc[
            index,
            "positive_fold_rate",
        ] = 0.0
        continue

    seed = row["seed"]

    condition_fold = (
        prediction_df[
            (prediction_df["seed"] == seed) & (prediction_df["condition"] == row["condition"])
        ]
        .groupby("fold")["absolute_error"]
        .mean()
    )

    baseline_fold = (
        prediction_df[(prediction_df["seed"] == seed) & (prediction_df["condition"] == "no_exog")]
        .groupby("fold")["absolute_error"]
        .mean()
    )

    common = condition_fold.index.intersection(baseline_fold.index)

    results_df.loc[
        index,
        "positive_fold_rate",
    ] = float((condition_fold.loc[common] < baseline_fold.loc[common]).mean())

results_df.to_csv(
    OUT / "tft_selected_exog_results.csv",
    index=False,
)

prediction_df.to_parquet(
    OUT / "tft_selected_exog_predictions.parquet",
    index=False,
)

summary = (
    results_df.groupby("condition")
    .agg(
        mean_mae=("mean_mae", "mean"),
        std_across_seeds=(
            "mean_mae",
            "std",
        ),
        mean_mse=("mean_mse", "mean"),
        mean_within_1=(
            "mean_within_1",
            "mean",
        ),
        mean_improvement_percent=(
            "mae_improvement_percent_vs_no_exog",
            "mean",
        ),
        mean_positive_fold_rate=(
            "positive_fold_rate",
            "mean",
        ),
    )
    .reset_index()
    .sort_values("mean_mae")
)

summary.to_csv(
    OUT / "tft_selected_exog_summary.csv",
    index=False,
)

(OUT / "experiment_config.json").write_text(
    json.dumps(
        {
            "run_id": RUN_ID,
            "n_windows": N_WINDOWS,
            "seeds": SEEDS,
            "conditions": CONDITIONS,
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("\n=== PER SEED ===")
print(
    results_df[
        [
            "seed",
            "condition",
            "mean_mae",
            "mean_mse",
            "mean_within_1",
            "mae_improvement_percent_vs_no_exog",
            "positive_fold_rate",
        ]
    ]
    .sort_values(["seed", "mean_mae"])
    .to_string(index=False)
)

print("\n=== SUMMARY ===")
print(summary.to_string(index=False))

print("\nOUT=", OUT)
print("TFT_SELECTED_EXOG_COMPARISON=PASS")
