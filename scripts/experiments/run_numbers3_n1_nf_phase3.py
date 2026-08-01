from __future__ import annotations

import gc
import json
import time
import traceback
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import torch
from neuralforecast import NeuralForecast
from neuralforecast.losses.pytorch import (
    DistributionLoss,
    MAE,
)
from neuralforecast.models import (
    Autoformer,
    DeepAR,
    DeepNPTS,
    FEDformer,
    Informer,
    KAN,
    NBEATSx,
)


ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = (
    ROOT
    / "data"
    / "exports"
    / "numbers3"
    / "splits"
    / "n1_holdout200_ordinal"
)

OUTPUT_DIR = (
    ROOT
    / "artifacts"
    / "numbers3"
    / "n1_nf_phase3"
)

HORIZON = 200
INPUT_SIZE = 256
MAX_STEPS = 20
SEED = 42


def trainer_kwargs() -> dict[str, Any]:
    return {
        "accelerator": "gpu",
        "devices": 1,
        "enable_progress_bar": False,
        "logger": False,
        "enable_model_summary": False,
    }


def common_kwargs() -> dict[str, Any]:
    return {
        "h": HORIZON,
        "input_size": INPUT_SIZE,
        "max_steps": MAX_STEPS,
        "learning_rate": 1e-3,
        "random_seed": SEED,
        "valid_loss": MAE(),
        "scaler_type": "standard",
        **trainer_kwargs(),
    }


def model_factories() -> list[tuple[str, Callable[[], Any]]]:
    return [
        (
            "Autoformer",
            lambda: Autoformer(
                hidden_size=16,
                n_head=4,
                encoder_layers=1,
                decoder_layers=1,
                MovingAvg_window=3,
                dropout=0.0,
                loss=MAE(),
                alias="numbers3_Autoformer",
                **common_kwargs(),
            ),
        ),
        (
            "FEDformer",
            lambda: FEDformer(
                hidden_size=16,
                n_head=8,
                encoder_layers=1,
                decoder_layers=1,
                MovingAvg_window=3,
                modes=4,
                dropout=0.0,
                loss=MAE(),
                alias="numbers3_FEDformer",
                **common_kwargs(),
            ),
        ),
        (
            "Informer",
            lambda: Informer(
                hidden_size=16,
                n_head=4,
                encoder_layers=1,
                decoder_layers=1,
                dropout=0.0,
                loss=MAE(),
                alias="numbers3_Informer",
                **common_kwargs(),
            ),
        ),
        (
            "DeepAR",
            lambda: DeepAR(
                lstm_hidden_size=16,
                lstm_n_layers=1,
                lstm_dropout=0.0,
                decoder_hidden_layers=0,
                decoder_hidden_size=0,
                trajectory_samples=10,
                loss=DistributionLoss(
                    distribution="Normal",
                    level=[80],
                    return_params=False,
                ),
                alias="numbers3_DeepAR",
                **common_kwargs(),
            ),
        ),
        (
            "DeepNPTS",
            lambda: DeepNPTS(
                hidden_size=16,
                n_layers=1,
                batch_norm=False,
                dropout=0.0,
                loss=MAE(),
                alias="numbers3_DeepNPTS",
                **common_kwargs(),
            ),
        ),
        (
            "KAN",
            lambda: KAN(
                hidden_size=16,
                n_hidden_layers=1,
                grid_size=5,
                spline_order=3,
                loss=MAE(),
                alias="numbers3_KAN",
                **common_kwargs(),
            ),
        ),
        (
            "NBEATSx",
            lambda: NBEATSx(
                stack_types=["identity"],
                n_blocks=[1],
                mlp_units=[[32, 32]],
                loss=MAE(),
                alias="numbers3_NBEATSx",
                **common_kwargs(),
            ),
        ),
    ]


def digitize(values: np.ndarray) -> np.ndarray:
    return np.clip(
        np.rint(values),
        0,
        9,
    ).astype(int)


def evaluate(
    name: str,
    actual: np.ndarray,
    raw: np.ndarray,
    fit_seconds: float,
    predict_seconds: float,
    peak_vram_mib: float,
) -> dict[str, Any]:
    digit = digitize(raw)

    raw_error = actual - raw
    digit_error = actual - digit

    return {
        "model": name,
        "status": "PASS",
        "raw_mae": float(
            np.mean(np.abs(raw_error))
        ),
        "raw_mse": float(
            np.mean(raw_error**2)
        ),
        "raw_rmse": float(
            np.sqrt(np.mean(raw_error**2))
        ),
        "digit_mae": float(
            np.mean(np.abs(digit_error))
        ),
        "digit_mse": float(
            np.mean(digit_error**2)
        ),
        "digit_rmse": float(
            np.sqrt(np.mean(digit_error**2))
        ),
        "within_1_rate": float(
            np.mean(np.abs(digit_error) <= 1)
        ),
        "exact_rate": float(
            np.mean(digit_error == 0)
        ),
        "prediction_min": float(raw.min()),
        "prediction_max": float(raw.max()),
        "prediction_mean": float(raw.mean()),
        "digit_prediction_mean": float(
            digit.mean()
        ),
        "fit_seconds": float(fit_seconds),
        "predict_seconds": float(
            predict_seconds
        ),
        "peak_vram_mib": float(
            peak_vram_mib
        ),
        "beats_digit_mae_baseline": bool(
            np.mean(np.abs(digit_error)) < 2.56
        ),
        "beats_within_1_baseline": bool(
            np.mean(np.abs(digit_error) <= 1)
            > 0.325
        ),
        "beats_exact_baseline": bool(
            np.mean(digit_error == 0) > 0.17
        ),
    }


def cleanup() -> None:
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    train = (
        pd.read_parquet(
            DATA_DIR / "train.parquet"
        )
        .sort_values("ds")
        .reset_index(drop=True)
    )

    test = (
        pd.read_parquet(
            DATA_DIR / "test.parquet"
        )
        .sort_values("ds")
        .reset_index(drop=True)
    )

    train = train[
        ["unique_id", "ds", "y"]
    ].copy()

    train["unique_id"] = (
        train["unique_id"].astype(str)
    )
    train["ds"] = train["ds"].astype(int)
    train["y"] = train["y"].astype(float)

    actual = test["y"].to_numpy(
        dtype=float
    )

    assert len(train) == 6839
    assert len(test) == 200
    assert torch.cuda.is_available()

    torch.set_float32_matmul_precision(
        "high"
    )

    rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []

    for name, factory in model_factories():
        print()
        print(f"START {name}")

        cleanup()

        try:
            torch.cuda.reset_peak_memory_stats()

            model = factory()

            nf = NeuralForecast(
                models=[model],
                freq=1,
            )

            fit_started = time.perf_counter()
            nf.fit(df=train)
            fit_seconds = (
                time.perf_counter()
                - fit_started
            )

            predict_started = (
                time.perf_counter()
            )
            forecast = nf.predict()
            predict_seconds = (
                time.perf_counter()
                - predict_started
            )

            columns = [
                column
                for column in forecast.columns
                if column
                not in {"unique_id", "ds"}
            ]

            median_columns = [
                column
                for column in columns
                if column.endswith("-median")
            ]

            base_columns = [
                column
                for column in columns
                if not column.endswith("-median")
                and "-lo-" not in column
                and "-hi-" not in column
            ]

            if len(median_columns) == 1:
                forecast_column = median_columns[0]
            elif len(base_columns) == 1:
                forecast_column = base_columns[0]
            elif len(columns) == 1:
                forecast_column = columns[0]
            else:
                raise RuntimeError(
                    f"Unable to select point forecast "
                    f"column from: {columns}"
                )

            raw = forecast[
                forecast_column
            ].to_numpy(dtype=float)

            if len(raw) != len(actual):
                raise RuntimeError(
                    f"Prediction length={len(raw)}, "
                    f"expected={len(actual)}"
                )

            if not np.isfinite(raw).all():
                raise RuntimeError(
                    "Non-finite predictions detected"
                )

            peak_vram_mib = (
                torch.cuda.max_memory_allocated()
                / 1024**2
            )

            result = evaluate(
                name=name,
                actual=actual,
                raw=raw,
                fit_seconds=fit_seconds,
                predict_seconds=predict_seconds,
                peak_vram_mib=peak_vram_mib,
            )

            rows.append(result)

            prediction_frames.append(
                pd.DataFrame(
                    {
                        "model": name,
                        "ds": test["ds"].to_numpy(),
                        "original_ds": test[
                            "original_ds"
                        ].to_numpy(),
                        "actual": actual,
                        "prediction_raw": raw,
                        "prediction_digit": (
                            digitize(raw)
                        ),
                    }
                )
            )

            print(
                name,
                "PASS",
                "digit_mae=",
                round(
                    result["digit_mae"],
                    6,
                ),
                "within_1_rate=",
                round(
                    result["within_1_rate"],
                    6,
                ),
                "exact_rate=",
                round(
                    result["exact_rate"],
                    6,
                ),
                "peak_vram_mib=",
                round(
                    peak_vram_mib,
                    2,
                ),
            )

        except Exception as exc:
            rows.append(
                {
                    "model": name,
                    "status": "FAIL",
                    "error_type": (
                        type(exc).__name__
                    ),
                    "error": str(exc),
                    "traceback": (
                        traceback.format_exc()
                    ),
                }
            )

            print(
                name,
                "FAIL",
                type(exc).__name__,
                str(exc),
            )

        finally:
            cleanup()

    results = pd.DataFrame(rows)

    sort_columns = [
        column
        for column in [
            "status",
            "digit_mae",
            "digit_mse",
            "model",
        ]
        if column in results.columns
    ]

    if sort_columns:
        results = results.sort_values(
            sort_columns,
            na_position="last",
        )

    csv_output = (
        OUTPUT_DIR
        / "numbers3_n1_nf_phase3_results.csv"
    )

    json_output = (
        OUTPUT_DIR
        / "numbers3_n1_nf_phase3_results.json"
    )

    predictions_output = (
        OUTPUT_DIR
        / "numbers3_n1_nf_phase3_predictions.parquet"
    )

    results.to_csv(
        csv_output,
        index=False,
    )

    json_output.write_text(
        json.dumps(
            rows,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    if prediction_frames:
        pd.concat(
            prediction_frames,
            ignore_index=True,
        ).to_parquet(
            predictions_output,
            index=False,
        )

    display_columns = [
        column
        for column in [
            "model",
            "status",
            "digit_mae",
            "digit_mse",
            "within_1_rate",
            "exact_rate",
            "fit_seconds",
            "predict_seconds",
            "peak_vram_mib",
            "beats_digit_mae_baseline",
            "beats_within_1_baseline",
            "beats_exact_baseline",
        ]
        if column in results.columns
    ]

    print()
    print("=== Phase 3 results ===")
    print(
        results[
            display_columns
        ].to_string(
            index=False,
            float_format=(
                lambda value: f"{value:.6f}"
            ),
        )
    )

    passed = int(
        (results["status"] == "PASS").sum()
    )
    failed = int(
        (results["status"] == "FAIL").sum()
    )

    print()
    print("models=", len(results))
    print("passed=", passed)
    print("failed=", failed)
    print("csv=", csv_output)
    print("json=", json_output)
    print(
        "predictions=",
        predictions_output,
    )

    if failed:
        print(
            "NUMBERS3_N1_NF_PHASE3=PARTIAL"
        )
    else:
        print(
            "NUMBERS3_N1_NF_PHASE3=PASS"
        )


if __name__ == "__main__":
    main()
