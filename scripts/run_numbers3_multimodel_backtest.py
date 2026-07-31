from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DIGIT_COLUMNS = ["d1", "d2", "d3"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Leakage-safe Numbers3 expanding-window multimodel backtest"
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("runs/data-acquisition-all/numbers3/normalized/numbers3.csv"),
    )
    parser.add_argument("--test-draws", type=int, default=30)
    parser.add_argument("--min-train-draws", type=int, default=1000)
    parser.add_argument("--lags", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--models",
        default=(
            "frequency,last,logistic,random-forest,"
            "extra-trees,hist-gradient-boosting,"
            "lightgbm,xgboost,catboost"
        ),
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def resolve_device(requested: str) -> str:
    if requested in {"cpu", "cuda"}:
        return requested

    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def load_data(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)

    frame = pd.read_csv(path)

    required = {"draw_no", "draw_date", *DIGIT_COLUMNS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    frame = frame.copy()
    frame["draw_date"] = pd.to_datetime(frame["draw_date"], errors="raise")

    for column in DIGIT_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(int)
        if not frame[column].between(0, 9).all():
            raise ValueError(f"{column} contains values outside 0..9")

    frame = (
        frame.sort_values("draw_no").drop_duplicates("draw_no", keep="last").reset_index(drop=True)
    )

    if not frame["draw_no"].is_monotonic_increasing:
        raise ValueError("draw_no is not monotonic")

    return frame


def build_features(frame: pd.DataFrame, lags: int) -> pd.DataFrame:
    features = pd.DataFrame(index=frame.index)

    features["draw_no"] = frame["draw_no"].astype(float)
    features["weekday"] = frame["draw_date"].dt.weekday.astype(float)
    features["month"] = frame["draw_date"].dt.month.astype(float)
    features["day"] = frame["draw_date"].dt.day.astype(float)

    features["weekday_sin"] = np.sin(2.0 * np.pi * features["weekday"] / 7.0)
    features["weekday_cos"] = np.cos(2.0 * np.pi * features["weekday"] / 7.0)
    features["month_sin"] = np.sin(2.0 * np.pi * features["month"] / 12.0)
    features["month_cos"] = np.cos(2.0 * np.pi * features["month"] / 12.0)

    for column in DIGIT_COLUMNS:
        shifted = frame[column].shift(1)

        for lag in range(1, lags + 1):
            features[f"{column}_lag_{lag}"] = frame[column].shift(lag)

        for window in (5, 10, 20, 50):
            features[f"{column}_mean_{window}"] = shifted.rolling(window).mean()
            features[f"{column}_std_{window}"] = shifted.rolling(window).std()
            features[f"{column}_min_{window}"] = shifted.rolling(window).min()
            features[f"{column}_max_{window}"] = shifted.rolling(window).max()

        features[f"{column}_change"] = frame[column].shift(1) - frame[column].shift(2)

    features["sum_lag_1"] = frame[DIGIT_COLUMNS].sum(axis=1).shift(1)
    features["range_lag_1"] = (
        frame[DIGIT_COLUMNS].max(axis=1) - frame[DIGIT_COLUMNS].min(axis=1)
    ).shift(1)

    return features.replace([np.inf, -np.inf], np.nan)


def make_model(
    model_id: str,
    seed: int,
    device: str,
) -> Any:
    if model_id == "logistic":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(
                max_iter=2000,
                random_state=seed,
            ),
        )

    if model_id == "random-forest":
        return RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=2,
            n_jobs=-1,
            random_state=seed,
        )

    if model_id == "extra-trees":
        return ExtraTreesClassifier(
            n_estimators=300,
            min_samples_leaf=2,
            n_jobs=-1,
            random_state=seed,
        )

    if model_id == "hist-gradient-boosting":
        return HistGradientBoostingClassifier(
            max_iter=200,
            learning_rate=0.05,
            max_leaf_nodes=31,
            random_state=seed,
        )

    if model_id == "lightgbm":
        from lightgbm import LGBMClassifier

        parameters: dict[str, Any] = {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "random_state": seed,
            "verbosity": -1,
        }
        if device == "cuda":
            parameters["device_type"] = "gpu"

        return LGBMClassifier(**parameters)

    if model_id == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="multi:softprob",
            num_class=10,
            tree_method="hist",
            device="cuda" if device == "cuda" else "cpu",
            random_state=seed,
            n_jobs=-1,
        )

    if model_id == "catboost":
        from catboost import CatBoostClassifier

        return CatBoostClassifier(
            iterations=300,
            learning_rate=0.05,
            depth=6,
            loss_function="MultiClass",
            task_type="GPU" if device == "cuda" else "CPU",
            devices="0" if device == "cuda" else None,
            random_seed=seed,
            verbose=False,
            allow_writing_files=False,
        )

    raise KeyError(model_id)


def predict_frequency(y_train: pd.Series) -> int:
    counts = y_train.value_counts()
    maximum = counts.max()
    return int(sorted(counts[counts == maximum].index)[0])


def predict_last(y_train: pd.Series) -> int:
    return int(y_train.iloc[-1])


def fit_predict_digit(
    model_id: str,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_test: pd.DataFrame,
    seed: int,
    device: str,
) -> int:
    if model_id == "frequency":
        return predict_frequency(y_train)

    if model_id == "last":
        return predict_last(y_train)

    model = make_model(model_id, seed, device)
    model.fit(x_train, y_train)
    prediction = model.predict(x_test)

    return int(np.asarray(prediction).reshape(-1)[0])


def evaluate_predictions(predictions: pd.DataFrame) -> dict[str, Any]:
    actual = predictions[["actual_d1", "actual_d2", "actual_d3"]].to_numpy(dtype=float)
    predicted = predictions[["pred_d1", "pred_d2", "pred_d3"]].to_numpy(dtype=float)

    error = np.abs(actual - predicted)

    return {
        "folds": int(len(predictions)),
        "straight_accuracy": float(np.mean(np.all(actual == predicted, axis=1))),
        "digit_accuracy": float(np.mean(actual == predicted)),
        "d1_accuracy": float(np.mean(actual[:, 0] == predicted[:, 0])),
        "d2_accuracy": float(np.mean(actual[:, 1] == predicted[:, 1])),
        "d3_accuracy": float(np.mean(actual[:, 2] == predicted[:, 2])),
        "within_1_rate": float(np.mean(error <= 1)),
        "all_3_within_1_rate": float(np.mean(np.all(error <= 1, axis=1))),
        "mae": float(np.mean(error)),
        "mse": float(np.mean((actual - predicted) ** 2)),
    }


def build_next_feature_row(
    frame: pd.DataFrame,
    lags: int,
) -> pd.DataFrame:
    next_date = frame["draw_date"].iloc[-1] + pd.Timedelta(days=1)
    next_row = {
        "draw_no": int(frame["draw_no"].iloc[-1]) + 1,
        "draw_date": next_date,
        "d1": np.nan,
        "d2": np.nan,
        "d3": np.nan,
    }

    extended = pd.concat(
        [frame, pd.DataFrame([next_row])],
        ignore_index=True,
    )
    return build_features(extended, lags).iloc[[-1]]


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)

    frame = load_data(args.data)
    features = build_features(frame, args.lags)

    valid_mask = features.notna().all(axis=1)
    valid_indices = np.flatnonzero(valid_mask.to_numpy())

    valid_indices = valid_indices[valid_indices >= args.min_train_draws]

    if len(valid_indices) < args.test_draws:
        raise RuntimeError(f"Only {len(valid_indices)} valid folds are available")

    test_indices = valid_indices[-args.test_draws :]
    requested_models = [value.strip() for value in args.models.split(",") if value.strip()]

    args.output.mkdir(parents=True, exist_ok=True)

    run_config = {
        "data": str(args.data),
        "rows": len(frame),
        "test_draws": args.test_draws,
        "min_train_draws": args.min_train_draws,
        "lags": args.lags,
        "seed": args.seed,
        "requested_device": args.device,
        "resolved_device": device,
        "models": requested_models,
    }
    (args.output / "run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary_rows: list[dict[str, Any]] = []
    all_predictions: list[pd.DataFrame] = []
    error_rows: list[dict[str, Any]] = []

    for model_id in requested_models:
        print(f"\n===== {model_id} =====")
        started = time.perf_counter()
        rows: list[dict[str, Any]] = []

        try:
            for fold_number, test_index in enumerate(test_indices, start=1):
                train_indices = np.flatnonzero(valid_mask.to_numpy()[:test_index])

                if len(train_indices) < args.min_train_draws:
                    continue

                x_train = features.iloc[train_indices]
                x_test = features.iloc[[test_index]]

                row: dict[str, Any] = {
                    "model_id": model_id,
                    "fold": fold_number,
                    "draw_no": int(frame.iloc[test_index]["draw_no"]),
                    "draw_date": str(frame.iloc[test_index]["draw_date"].date()),
                }

                for digit_column in DIGIT_COLUMNS:
                    prediction = fit_predict_digit(
                        model_id=model_id,
                        x_train=x_train,
                        y_train=frame.iloc[train_indices][digit_column],
                        x_test=x_test,
                        seed=args.seed + fold_number,
                        device=device,
                    )
                    row[f"actual_{digit_column}"] = int(frame.iloc[test_index][digit_column])
                    row[f"pred_{digit_column}"] = prediction

                rows.append(row)
                print(
                    f"{fold_number:3d}/{len(test_indices)} "
                    f"draw={row['draw_no']} "
                    f"actual={row['actual_d1']}{row['actual_d2']}{row['actual_d3']} "
                    f"pred={row['pred_d1']}{row['pred_d2']}{row['pred_d3']}"
                )

            model_predictions = pd.DataFrame(rows)
            metrics = evaluate_predictions(model_predictions)
            metrics.update(
                {
                    "model_id": model_id,
                    "status": "OK",
                    "duration_seconds": (time.perf_counter() - started),
                    "device": device,
                }
            )
            summary_rows.append(metrics)
            all_predictions.append(model_predictions)

        except Exception as exc:
            error_rows.append(
                {
                    "model_id": model_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            summary_rows.append(
                {
                    "model_id": model_id,
                    "status": "ERROR",
                    "duration_seconds": (time.perf_counter() - started),
                    "device": device,
                    "error": str(exc),
                }
            )
            print(f"ERROR: {type(exc).__name__}: {exc}")

    summary = pd.DataFrame(summary_rows)

    if "mae" in summary.columns:
        summary = summary.sort_values(
            ["status", "mae", "straight_accuracy"],
            ascending=[False, True, False],
            na_position="last",
        )

    summary.to_csv(args.output / "summary.csv", index=False)

    if all_predictions:
        pd.concat(all_predictions, ignore_index=True).to_csv(
            args.output / "predictions.csv",
            index=False,
        )

    if error_rows:
        pd.DataFrame(error_rows).to_csv(
            args.output / "errors.csv",
            index=False,
        )

    next_features = build_next_feature_row(frame, args.lags)
    full_train_indices = np.flatnonzero(valid_mask.to_numpy())

    next_predictions: list[dict[str, Any]] = []

    for model_id in requested_models:
        if model_id in set(summary.loc[summary["status"] != "OK", "model_id"]):
            continue

        next_row: dict[str, Any] = {
            "model_id": model_id,
            "next_draw_no": int(frame["draw_no"].iloc[-1]) + 1,
            "device": device,
        }

        try:
            for digit_column in DIGIT_COLUMNS:
                next_row[f"pred_{digit_column}"] = fit_predict_digit(
                    model_id=model_id,
                    x_train=features.iloc[full_train_indices],
                    y_train=frame.iloc[full_train_indices][digit_column],
                    x_test=next_features,
                    seed=args.seed,
                    device=device,
                )

            next_row["prediction"] = (
                f"{next_row['pred_d1']}{next_row['pred_d2']}{next_row['pred_d3']}"
            )
            next_predictions.append(next_row)
        except Exception as exc:
            error_rows.append(
                {
                    "model_id": model_id,
                    "error_type": type(exc).__name__,
                    "message": f"next prediction failed: {exc}",
                }
            )

    pd.DataFrame(next_predictions).to_csv(
        args.output / "next_predictions.csv",
        index=False,
    )

    print("\n===== SUMMARY =====")
    display_columns = [
        column
        for column in [
            "model_id",
            "status",
            "straight_accuracy",
            "digit_accuracy",
            "within_1_rate",
            "all_3_within_1_rate",
            "mae",
            "mse",
            "duration_seconds",
            "device",
        ]
        if column in summary.columns
    ]
    print(summary[display_columns].to_string(index=False))

    print(f"\nOutput: {args.output}")


if __name__ == "__main__":
    main()
