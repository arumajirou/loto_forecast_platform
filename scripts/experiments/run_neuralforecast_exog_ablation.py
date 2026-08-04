from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from neuralforecast import NeuralForecast
from neuralforecast.losses.pytorch import MAE
from neuralforecast.models import (
    GRU,
    LSTM,
    NHITS,
    TCN,
    TFT,
    NBEATSx,
    TiDE,
)
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = time.strftime("nf-exog-ablation-%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / "experiments" / RUN_ID
OUT.mkdir(parents=True, exist_ok=False)

GAME = "loto7"
H = 1
INPUT_SIZE = 64
MAX_STEPS = 100
N_WINDOWS = 5
SEED = 42

FUTURE_EXOG = [
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

HISTORICAL_EXOG = [
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

db_url = (
    f"postgresql+psycopg://{os.environ['DB_USER']}:"
    f"{os.environ['DB_PASSWORD']}@"
    f"{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/"
    f"{os.environ['DB_NAME']}"
)

engine = create_engine(db_url)

columns = [
    "unique_id",
    "ds",
    "y",
    *FUTURE_EXOG,
    *HISTORICAL_EXOG,
]

df = pd.read_sql(
    f"""
    SELECT {", ".join(columns)}
    FROM dataset.loto_y_ts_unified
    WHERE loto = '{GAME}'
      AND ts_type = 'raw'
    ORDER BY unique_id, ds
    """,
    engine,
)

df["actual_ds"] = pd.to_datetime(df["ds"])
df["draw_index"] = df.groupby("unique_id").cumcount()

# NeuralForecastにも規則的なインデックスを使用する。
df["ds"] = pd.Timestamp("2000-01-01") + pd.to_timedelta(df["draw_index"], unit="D")

df["y"] = pd.to_numeric(df["y"], errors="coerce")

for column in FUTURE_EXOG + HISTORICAL_EXOG:
    df[column] = pd.to_numeric(
        df[column],
        errors="coerce",
    )

df = df.replace([np.inf, -np.inf], np.nan)

# historical exogの初期欠損行を除去。
df = df.dropna(subset=["y", *FUTURE_EXOG, *HISTORICAL_EXOG]).reset_index(drop=True)

conditions = {
    "no_exog": {
        "futr": [],
        "hist": [],
        "stat": [],
    },
    "calendar_exog": {
        "futr": FUTURE_EXOG,
        "hist": [],
        "stat": [],
    },
    "all_exog": {
        "futr": FUTURE_EXOG,
        "hist": HISTORICAL_EXOG,
        "stat": [],
    },
}

MODEL_BUILDERS = {
    "nhits": lambda exog: NHITS(
        h=H,
        input_size=INPUT_SIZE,
        max_steps=MAX_STEPS,
        learning_rate=1e-3,
        loss=MAE(),
        futr_exog_list=exog["futr"],
        hist_exog_list=exog["hist"],
        stat_exog_list=exog["stat"],
        scaler_type="robust",
        batch_size=32,
        random_seed=SEED,
    ),
    "nbeatsx": lambda exog: NBEATSx(
        h=H,
        input_size=INPUT_SIZE,
        stack_types=["identity"],
        n_blocks=[1],
        mlp_units=[[128, 128]],
        max_steps=MAX_STEPS,
        learning_rate=1e-3,
        loss=MAE(),
        futr_exog_list=exog["futr"],
        hist_exog_list=exog["hist"],
        stat_exog_list=exog["stat"],
        scaler_type="robust",
        batch_size=32,
        random_seed=SEED,
    ),
    "tft": lambda exog: TFT(
        h=H,
        input_size=INPUT_SIZE,
        max_steps=MAX_STEPS,
        learning_rate=1e-3,
        loss=MAE(),
        futr_exog_list=exog["futr"],
        hist_exog_list=exog["hist"],
        stat_exog_list=exog["stat"],
        scaler_type="robust",
        batch_size=32,
        random_seed=SEED,
    ),
    "tide": lambda exog: TiDE(
        h=H,
        input_size=INPUT_SIZE,
        max_steps=MAX_STEPS,
        learning_rate=1e-3,
        loss=MAE(),
        futr_exog_list=exog["futr"],
        hist_exog_list=exog["hist"],
        stat_exog_list=exog["stat"],
        scaler_type="robust",
        batch_size=32,
        random_seed=SEED,
    ),
    "tcn": lambda exog: TCN(
        h=H,
        input_size=INPUT_SIZE,
        max_steps=MAX_STEPS,
        learning_rate=1e-3,
        loss=MAE(),
        futr_exog_list=exog["futr"],
        hist_exog_list=exog["hist"],
        stat_exog_list=exog["stat"],
        scaler_type="robust",
        batch_size=32,
        random_seed=SEED,
    ),
    "gru": lambda exog: GRU(
        h=H,
        input_size=INPUT_SIZE,
        max_steps=MAX_STEPS,
        learning_rate=1e-3,
        loss=MAE(),
        futr_exog_list=exog["futr"],
        hist_exog_list=exog["hist"],
        stat_exog_list=exog["stat"],
        scaler_type="robust",
        batch_size=32,
        random_seed=SEED,
    ),
    "lstm": lambda exog: LSTM(
        h=H,
        input_size=INPUT_SIZE,
        max_steps=MAX_STEPS,
        learning_rate=1e-3,
        loss=MAE(),
        futr_exog_list=exog["futr"],
        hist_exog_list=exog["hist"],
        stat_exog_list=exog["stat"],
        scaler_type="robust",
        batch_size=32,
        random_seed=SEED,
    ),
}

results = []
prediction_rows = []

for model_name, builder in MODEL_BUILDERS.items():
    for condition, exog in conditions.items():
        run_dir = OUT / model_name / condition
        run_dir.mkdir(parents=True, exist_ok=True)

        selected_cols = [
            "unique_id",
            "ds",
            "y",
            *exog["futr"],
            *exog["hist"],
        ]
        selected_cols = list(dict.fromkeys(selected_cols))
        model_df = df[selected_cols].copy()

        common_dates = sorted(
            set.intersection(*[set(group["ds"]) for _, group in model_df.groupby("unique_id")])
        )

        test_dates = common_dates[-N_WINDOWS:]
        fold_mae = []
        fold_mse = []
        fold_within1 = []

        start = time.perf_counter()

        for fold, test_date in enumerate(test_dates, start=1):
            train_df = model_df[model_df["ds"] < test_date]
            test_df = model_df[model_df["ds"] == test_date]

            model = builder(exog)

            nf = NeuralForecast(
                models=[model],
                freq="D",
            )

            nf.fit(df=train_df)

            if exog["futr"]:
                futr_df = test_df[["unique_id", "ds", *exog["futr"]]].copy()
                forecast = nf.predict(futr_df=futr_df)
            else:
                forecast = nf.predict()

            prediction_column = [
                column for column in forecast.columns if column not in {"unique_id", "ds"}
            ][0]

            merged = test_df[["unique_id", "ds", "y"]].merge(
                forecast[["unique_id", "ds", prediction_column]],
                on=["unique_id", "ds"],
                how="inner",
            )

            actual = merged["y"].to_numpy(dtype=float)
            prediction = merged[prediction_column].to_numpy(dtype=float)

            errors = np.abs(actual - prediction)

            fold_mae.append(float(np.mean(errors)))
            fold_mse.append(float(np.mean((actual - prediction) ** 2)))
            fold_within1.append(float(np.mean(errors <= 1.0)))

            for index, row in merged.iterrows():
                prediction_rows.append(
                    {
                        "model": model_name,
                        "condition": condition,
                        "fold": fold,
                        "unique_id": row["unique_id"],
                        "ds": str(row["ds"]),
                        "actual": float(row["y"]),
                        "prediction": float(row[prediction_column]),
                        "absolute_error": float(abs(row["y"] - row[prediction_column])),
                    }
                )

        elapsed = time.perf_counter() - start

        # 全データで最終学習して保存。
        final_model = builder(exog)
        final_nf = NeuralForecast(
            models=[final_model],
            freq="D",
        )
        final_nf.fit(df=model_df)

        save_path = run_dir / "saved_model"
        final_nf.save(
            path=str(save_path),
            overwrite=True,
            save_dataset=True,
        )

        model_files = [path for path in save_path.rglob("*") if path.is_file()]

        hashes = {
            str(path.relative_to(run_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in model_files
        }

        properties = {
            "model": model_name,
            "condition": condition,
            "futr_exog_list": exog["futr"],
            "hist_exog_list": exog["hist"],
            "stat_exog_list": exog["stat"],
            "training_rows": len(model_df),
            "cv_windows": N_WINDOWS,
            "mean_mae": float(np.mean(fold_mae)),
            "mean_mse": float(np.mean(fold_mse)),
            "mean_within_1": float(np.mean(fold_within1)),
            "training_seconds": elapsed,
            "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu_name": (torch.cuda.get_device_name(0) if torch.cuda.is_available() else None),
            "python": platform.python_version(),
            "saved_model_path": str(save_path),
        }

        (run_dir / "model_properties.json").write_text(
            json.dumps(properties, indent=2),
            encoding="utf-8",
        )

        (run_dir / "SHA256SUMS.json").write_text(
            json.dumps(hashes, indent=2),
            encoding="utf-8",
        )

        results.append(properties)

results_df = pd.DataFrame(results)

for model_name in results_df["model"].unique():
    baseline = float(
        results_df.loc[
            (results_df["model"] == model_name) & (results_df["condition"] == "no_exog"),
            "mean_mae",
        ].iloc[0]
    )

    mask = results_df["model"] == model_name

    results_df.loc[
        mask,
        "mae_improvement_percent_vs_no_exog",
    ] = (baseline - results_df.loc[mask, "mean_mae"]) / baseline * 100.0

results_df.to_csv(
    OUT / "neuralforecast_exog_results.csv",
    index=False,
)

pd.DataFrame(prediction_rows).to_parquet(
    OUT / "neuralforecast_exog_predictions.parquet",
    index=False,
)

(OUT / "neuralforecast_exog_results.json").write_text(
    json.dumps(
        results_df.to_dict(orient="records"),
        indent=2,
    ),
    encoding="utf-8",
)

print(
    results_df[
        [
            "model",
            "condition",
            "mean_mae",
            "mean_mse",
            "mean_within_1",
            "mae_improvement_percent_vs_no_exog",
        ]
    ]
    .sort_values("mean_mae")
    .to_string(index=False)
)

print("OUT=", OUT)
print("NEURALFORECAST_EXOG_ABLATION=PASS")
