from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from pathlib import Path

import pandas as pd
import torch
from autogluon.timeseries import (
    TimeSeriesDataFrame,
    TimeSeriesPredictor,
)
from sqlalchemy import create_engine

ROOT = Path("/mnt/e/env/ts/loto_forecast_platform")
RUN_ID = time.strftime("chronos2-exog-%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / "models" / RUN_ID
OUT.mkdir(parents=True, exist_ok=False)

PREDICTION_LENGTH = 1
ITEM_LIMIT = 7
ROW_LIMIT_PER_ITEM = 512
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
SELECT
    item_id,
    actual_date,
    target,
    day_of_week,
    month_of_year,
    day_of_month,
    day_of_year
FROM selected
WHERE reverse_row <= {ROW_LIMIT_PER_ITEM}
ORDER BY item_id, actual_date
"""

df = pd.read_sql(query, engine)

if df.empty:
    raise RuntimeError("No training data was loaded")

selected_items = list(df["item_id"].drop_duplicates())[:ITEM_LIMIT]
df = df[df["item_id"].isin(selected_items)].copy()

df["actual_date"] = pd.to_datetime(df["actual_date"])
df["target"] = pd.to_numeric(df["target"], errors="raise")

# Chronological draw number inside each position series.
df["draw_index"] = df.groupby("item_id").cumcount()

# AutoGluon requires a regular timestamp index.
# Preserve actual calendar information in covariate columns.
base_timestamp = pd.Timestamp("2000-01-01")
df["timestamp"] = base_timestamp + pd.to_timedelta(df["draw_index"], unit="D")

df["days_since_previous_draw"] = (
    df.groupby("item_id")["actual_date"].diff().dt.days.fillna(0).astype(float)
)

for column in [
    "day_of_week",
    "month_of_year",
    "day_of_month",
    "day_of_year",
    "days_since_previous_draw",
]:
    df[column] = pd.to_numeric(df[column], errors="raise")

model_df = df[
    [
        "item_id",
        "timestamp",
        "target",
        "day_of_week",
        "month_of_year",
        "day_of_month",
        "day_of_year",
        "days_since_previous_draw",
    ]
].copy()

tsdf = TimeSeriesDataFrame.from_data_frame(
    model_df,
    id_column="item_id",
    timestamp_column="timestamp",
)

print("inferred_frequency=", tsdf.infer_frequency())

train_data = tsdf.slice_by_timestep(None, -PREDICTION_LENGTH)
test_data = tsdf.slice_by_timestep(-PREDICTION_LENGTH, None)

known_covariate_names = [
    "day_of_week",
    "month_of_year",
    "day_of_month",
    "day_of_year",
    "days_since_previous_draw",
]

known_covariates = test_data[known_covariate_names].copy()

# Save before training, so failed training runs remain diagnosable.
tsdf.to_pickle(OUT / "evaluation_data.pkl")
df.to_parquet(OUT / "source_data.parquet", index=False)

predictor_path = OUT / "predictor"

predictor = TimeSeriesPredictor(
    path=str(predictor_path),
    prediction_length=PREDICTION_LENGTH,
    target="target",
    known_covariates_names=known_covariate_names,
    eval_metric="MAE",
    freq="D",
)

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
    enable_ensemble=False,
)

train_seconds = time.perf_counter() - start

pred = predictor.predict(
    train_data,
    known_covariates=known_covariates,
)

score = predictor.evaluate(tsdf)

pred_df = pred.to_data_frame()
pred_df.to_parquet(OUT / "predictions.parquet")

try:
    importance = predictor.feature_importance(
        data=tsdf,
        features=known_covariate_names,
    )
    importance.to_csv(OUT / "feature_importance.csv")
    importance_status = "PASS"
except Exception as exc:
    importance = None
    importance_status = f"UNAVAILABLE: {type(exc).__name__}: {exc}"

loaded = TimeSeriesPredictor.load(str(predictor_path))

pred_loaded = loaded.predict(
    train_data,
    known_covariates=known_covariates,
)

before = pred.to_data_frame().select_dtypes("number")
after = pred_loaded.to_data_frame().select_dtypes("number")

max_abs_diff = float(before.subtract(after).abs().to_numpy().max())

model_files = sorted(path for path in predictor_path.rglob("*") if path.is_file())

hashes = {}
for path in model_files:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes[str(path.relative_to(OUT))] = digest

gpu_info = {
    "cuda_available": torch.cuda.is_available(),
    "torch_version": torch.__version__,
    "cuda_version": torch.version.cuda,
    "device_count": torch.cuda.device_count(),
}

if torch.cuda.is_available():
    gpu_info.update(
        {
            "device_name": torch.cuda.get_device_name(0),
            "allocated_bytes": torch.cuda.memory_allocated(0),
            "reserved_bytes": torch.cuda.memory_reserved(0),
            "max_allocated_bytes": torch.cuda.max_memory_allocated(0),
            "max_reserved_bytes": torch.cuda.max_memory_reserved(0),
        }
    )

metadata = {
    "run_id": RUN_ID,
    "model": "Chronos2",
    "model_path": MODEL_PATH,
    "fine_tune": True,
    "fine_tune_mode": "lora",
    "fine_tune_steps": 20,
    "prediction_length": PREDICTION_LENGTH,
    "frequency": "synthetic-draw-index-D",
    "known_covariates": known_covariate_names,
    "rows": len(df),
    "items": len(selected_items),
    "train_seconds": train_seconds,
    "score": score,
    "feature_importance_status": importance_status,
    "reload_max_abs_diff": max_abs_diff,
    "python": platform.python_version(),
    "gpu": gpu_info,
    "model_file_count": len(model_files),
}

(OUT / "model_properties.json").write_text(
    json.dumps(metadata, indent=2, default=str),
    encoding="utf-8",
)

(OUT / "SHA256SUMS.json").write_text(
    json.dumps(hashes, indent=2),
    encoding="utf-8",
)

print("RUN_ID=", RUN_ID)
print("OUT=", OUT)
print("ROWS=", len(df))
print("ITEMS=", len(selected_items))
print("TRAIN_SECONDS=", train_seconds)
print("SCORE=", score)
print("FEATURE_IMPORTANCE_STATUS=", importance_status)

if importance is not None:
    print("FEATURE_IMPORTANCE=")
    print(importance)

print("RELOAD_MAX_ABS_DIFF=", max_abs_diff)
print("GPU_INFO=", gpu_info)

if max_abs_diff > 1e-5:
    raise RuntimeError(f"Reload prediction mismatch: {max_abs_diff}")

print("CHRONOS2_EXOG_SMOKE=PASS")
