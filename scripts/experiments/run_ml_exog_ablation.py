from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine

from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor


ROOT = Path("/mnt/e/env/ts/loto_forecast_platform")
RUN_ID = time.strftime("ml-exog-ablation-%Y%m%d-%H%M%S")
OUT = ROOT / "artifacts" / "experiments" / RUN_ID
OUT.mkdir(parents=True, exist_ok=False)

GAME = "loto7"
TS_TYPE = "raw"
N_WINDOWS = 5
SEED = 42

ID_COLS = ["loto", "unique_id", "ts_type", "ds", "y"]

# 予測時点で確実に決定できるカレンダー特徴。
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

# 各行の予測時点までのデータから作成された過去特徴。
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
    "hist_roll_min_7",
    "hist_roll_max_7",
    "hist_roll_min_14",
    "hist_roll_max_14",
    "hist_expanding_mean",
    "hist_expanding_std",
    "hist_ewm_mean_7",
    "hist_ewm_mean_14",
]

EXOG_COLS = FUTURE_EXOG + HISTORICAL_EXOG

MODELS = {
    "ridge": Pipeline(
        [
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=1.0)),
        ]
    ),
    "elasticnet": Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                ElasticNet(
                    alpha=0.01,
                    l1_ratio=0.5,
                    max_iter=10000,
                    random_state=SEED,
                ),
            ),
        ]
    ),
    "random_forest": RandomForestRegressor(
        n_estimators=300,
        min_samples_leaf=3,
        n_jobs=-1,
        random_state=SEED,
    ),
    "extra_trees": ExtraTreesRegressor(
        n_estimators=300,
        min_samples_leaf=2,
        n_jobs=-1,
        random_state=SEED,
    ),
    "hist_gradient_boosting": HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.05,
        random_state=SEED,
    ),
    "lightgbm": LGBMRegressor(
        n_estimators=400,
        learning_rate=0.03,
        num_leaves=31,
        random_state=SEED,
        verbosity=-1,
    ),
    "xgboost": XGBRegressor(
        n_estimators=400,
        learning_rate=0.03,
        max_depth=5,
        objective="reg:squarederror",
        n_jobs=-1,
        random_state=SEED,
    ),
    "catboost": CatBoostRegressor(
        iterations=400,
        learning_rate=0.03,
        depth=6,
        loss_function="MAE",
        verbose=False,
        random_seed=SEED,
    ),
}

db_url = (
    f"postgresql+psycopg://{os.environ['DB_USER']}:"
    f"{os.environ['DB_PASSWORD']}@"
    f"{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/"
    f"{os.environ['DB_NAME']}"
)

engine = create_engine(db_url)

selected_columns = ID_COLS + EXOG_COLS

sql = f"""
SELECT {", ".join(selected_columns)}
FROM dataset.loto_y_ts_unified
WHERE loto = '{GAME}'
  AND ts_type = '{TS_TYPE}'
ORDER BY unique_id, ds
"""

df = pd.read_sql(sql, engine)
df["ds"] = pd.to_datetime(df["ds"])
df["y"] = pd.to_numeric(df["y"], errors="coerce")

for column in EXOG_COLS:
    df[column] = pd.to_numeric(df[column], errors="coerce")

# 外生変数なし条件でも、自己回帰情報としてlag_1だけは使用する。
# 完全に特徴0個ではsklearnモデルを学習できないため。
BASE_COLS = ["hist_lag_1"]

conditions = {
    "no_exog": BASE_COLS,
    "calendar_exog": BASE_COLS + FUTURE_EXOG,
    "historical_exog": BASE_COLS + HISTORICAL_EXOG,
    "all_exog": BASE_COLS + EXOG_COLS,
}

# 重複列を除去。
conditions = {
    key: list(dict.fromkeys(columns))
    for key, columns in conditions.items()
}

results: list[dict] = []
prediction_rows: list[dict] = []

for model_name, prototype in MODELS.items():
    for condition, feature_cols in conditions.items():
        condition_dir = OUT / model_name / condition
        condition_dir.mkdir(parents=True, exist_ok=True)

        working = df[
            ["unique_id", "ds", "y"] + feature_cols
        ].copy()

        working = working.replace([np.inf, -np.inf], np.nan)
        working = working.dropna(
            subset=["y", *feature_cols]
        ).reset_index(drop=True)

        series_dates = {
            unique_id: list(group["ds"].sort_values().unique())
            for unique_id, group in working.groupby("unique_id")
        }

        common_dates = sorted(
            set.intersection(
                *[set(dates) for dates in series_dates.values()]
            )
        )

        test_dates = common_dates[-N_WINDOWS:]

        fold_maes = []
        fold_mses = []
        fold_within1 = []

        start = time.perf_counter()

        for fold, test_date in enumerate(test_dates, start=1):
            train = working[working["ds"] < test_date]
            test = working[working["ds"] == test_date]

            if train.empty or test.empty:
                raise RuntimeError(
                    f"empty fold model={model_name} "
                    f"condition={condition} date={test_date}"
                )

            estimator = clone(prototype)
            estimator.fit(
                train[feature_cols],
                train["y"],
            )

            prediction = np.asarray(
                estimator.predict(test[feature_cols]),
                dtype=float,
            )

            actual = test["y"].to_numpy(dtype=float)

            mae = mean_absolute_error(actual, prediction)
            mse = mean_squared_error(actual, prediction)
            within1 = float(
                np.mean(np.abs(actual - prediction) <= 1.0)
            )

            fold_maes.append(float(mae))
            fold_mses.append(float(mse))
            fold_within1.append(within1)

            for index, (_, row) in enumerate(test.iterrows()):
                prediction_rows.append(
                    {
                        "model": model_name,
                        "condition": condition,
                        "fold": fold,
                        "ds": str(test_date),
                        "unique_id": row["unique_id"],
                        "actual": float(actual[index]),
                        "prediction": float(prediction[index]),
                        "absolute_error": float(
                            abs(actual[index] - prediction[index])
                        ),
                        "within_1": bool(
                            abs(actual[index] - prediction[index]) <= 1
                        ),
                    }
                )

        elapsed = time.perf_counter() - start

        # 最終モデルは全データで再学習して保存。
        final_model = clone(prototype)
        final_model.fit(
            working[feature_cols],
            working["y"],
        )

        model_path = condition_dir / "model.joblib"
        joblib.dump(final_model, model_path)

        importance_df = None

        try:
            perm = permutation_importance(
                final_model,
                working[feature_cols].tail(1000),
                working["y"].tail(1000),
                n_repeats=5,
                random_state=SEED,
                scoring="neg_mean_absolute_error",
            )
            importance_df = pd.DataFrame(
                {
                    "feature": feature_cols,
                    "importance_mean": perm.importances_mean,
                    "importance_std": perm.importances_std,
                }
            ).sort_values(
                "importance_mean",
                ascending=False,
            )
            importance_df.to_csv(
                condition_dir / "feature_importance.csv",
                index=False,
            )
        except Exception as exc:
            (
                condition_dir / "feature_importance_error.txt"
            ).write_text(
                f"{type(exc).__name__}: {exc}",
                encoding="utf-8",
            )

        digest = hashlib.sha256(
            model_path.read_bytes()
        ).hexdigest()

        properties = {
            "model": model_name,
            "condition": condition,
            "feature_columns": feature_cols,
            "training_rows": len(working),
            "cv_windows": N_WINDOWS,
            "mean_mae": float(np.mean(fold_maes)),
            "mean_mse": float(np.mean(fold_mses)),
            "mean_within_1": float(np.mean(fold_within1)),
            "training_seconds": elapsed,
            "model_path": str(model_path),
            "model_sha256": digest,
            "python": platform.python_version(),
        }

        (
            condition_dir / "model_properties.json"
        ).write_text(
            json.dumps(properties, indent=2),
            encoding="utf-8",
        )

        results.append(properties)

results_df = pd.DataFrame(results)

for model_name in results_df["model"].unique():
    baseline = float(
        results_df.loc[
            (results_df["model"] == model_name)
            & (results_df["condition"] == "no_exog"),
            "mean_mae",
        ].iloc[0]
    )

    mask = results_df["model"] == model_name
    results_df.loc[
        mask,
        "mae_improvement_percent_vs_no_exog",
    ] = (
        (
            baseline
            - results_df.loc[mask, "mean_mae"]
        )
        / baseline
        * 100.0
    )

results_df.to_csv(
    OUT / "ml_exog_results.csv",
    index=False,
)

pd.DataFrame(prediction_rows).to_parquet(
    OUT / "ml_exog_predictions.parquet",
    index=False,
)

(OUT / "ml_exog_results.json").write_text(
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
print("ML_EXOG_ABLATION=PASS")
