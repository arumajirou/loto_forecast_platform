from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = time.strftime("chronos2-exog-ablation-%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / "experiments" / RUN_ID
OUT.mkdir(parents=True, exist_ok=False)

H = 1
ROW_LIMIT = 512
MODEL_PATH = "amazon/chronos-2"

db_url = (
    f"postgresql+psycopg://{os.environ['DB_USER']}:"
    f"{os.environ['DB_PASSWORD']}@"
    f"{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/"
    f"{os.environ['DB_NAME']}"
)

engine = create_engine(db_url)

query = f"""
WITH selected AS (
    SELECT
        unique_id AS item_id,
        ds::timestamp AS actual_date,
        y::double precision AS target,
        EXTRACT(DOW FROM ds)::double precision AS day_of_week,
        EXTRACT(MONTH FROM ds)::double precision AS month_of_year,
        EXTRACT(DAY FROM ds)::double precision AS day_of_month,
        EXTRACT(DOY FROM ds)::double precision AS day_of_year,
        ROW_NUMBER() OVER (
            PARTITION BY unique_id
            ORDER BY ds DESC
        ) AS reverse_row
    FROM dataset.loto_y_ts_unified
    WHERE loto = 'loto7'
      AND ts_type = 'raw'
)
SELECT *
FROM selected
WHERE reverse_row <= {ROW_LIMIT}
ORDER BY item_id, actual_date
"""

df = pd.read_sql(query, engine)

df["actual_date"] = pd.to_datetime(df["actual_date"])
df["draw_index"] = df.groupby("item_id").cumcount()
df["timestamp"] = pd.Timestamp("2000-01-01") + pd.to_timedelta(df["draw_index"], unit="D")

df["days_since_previous_draw"] = (
    df.groupby("item_id")["actual_date"].diff().dt.days.fillna(0).astype(float)
)

exog_cols = [
    "day_of_week",
    "month_of_year",
    "day_of_month",
    "day_of_year",
    "days_since_previous_draw",
]

base_cols = ["item_id", "timestamp", "target"]
model_df = df[base_cols + exog_cols].copy()

tsdf = TimeSeriesDataFrame.from_data_frame(
    model_df,
    id_column="item_id",
    timestamp_column="timestamp",
)

conditions = {
    "no_exog": [],
    "with_exog": exog_cols,
    "shifted_exog": exog_cols,
}

results = []

for condition, known_cols in conditions.items():
    condition_data = tsdf.copy()

    if condition == "shifted_exog":
        shifted = condition_data.to_data_frame().copy()

        for column in exog_cols:
            shifted[column] = shifted.groupby(level="item_id")[column].shift(1).bfill()

        condition_data = TimeSeriesDataFrame(shifted)

    predictor_path = OUT / condition / "predictor"
    predictor_path.parent.mkdir(parents=True, exist_ok=True)

    kwargs = {
        "path": str(predictor_path),
        "prediction_length": H,
        "target": "target",
        "eval_metric": "MAE",
        "freq": "D",
    }

    if known_cols:
        kwargs["known_covariates_names"] = known_cols

    predictor = TimeSeriesPredictor(**kwargs)

    train_data = condition_data.slice_by_timestep(None, -H)

    start = time.perf_counter()

    predictor.fit(
        train_data=train_data,
        hyperparameters={
            "Chronos2": {
                "model_path": MODEL_PATH,
                "fine_tune": True,
                "fine_tune_mode": "lora",
                "fine_tune_steps": 20,
                "batch_size": 4,
            }
        },
        num_val_windows=5,
        val_step_size=1,
        refit_every_n_windows=None,
        enable_ensemble=False,
        random_seed=123,
    )

    elapsed = time.perf_counter() - start
    score = predictor.evaluate(condition_data)

    mae = abs(float(score["MAE"]))

    results.append(
        {
            "condition": condition,
            "mae": mae,
            "elapsed_seconds": elapsed,
            "known_covariates": known_cols,
        }
    )

results_df = pd.DataFrame(results)

baseline = float(
    results_df.loc[
        results_df["condition"] == "no_exog",
        "mae",
    ].iloc[0]
)

results_df["improvement_percent_vs_no_exog"] = (baseline - results_df["mae"]) / baseline * 100.0

results_df.to_csv(OUT / "ablation_results.csv", index=False)

(OUT / "ablation_results.json").write_text(
    json.dumps(
        results_df.to_dict(orient="records"),
        indent=2,
    ),
    encoding="utf-8",
)

print(results_df.to_string(index=False))
print("OUT=", OUT)
print("CHRONOS2_EXOG_ABLATION=PASS")
