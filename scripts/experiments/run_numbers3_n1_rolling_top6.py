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
from neuralforecast.losses.pytorch import MAE
from neuralforecast.models import (
    Informer,
    KAN,
    MLP,
    NLinear,
    TCN,
    TimesNet,
)


ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    ROOT
    / "data"
    / "exports"
    / "numbers3"
    / "numbers3_n1.parquet"
)

OUTPUT_DIR = (
    ROOT
    / "artifacts"
    / "numbers3"
    / "n1_rolling_top6"
)

ROLLING_POINTS = 50
INPUT_SIZE = 256
MAX_STEPS = 20
SEED = 42


def trainer_kwargs() -> dict[str, Any]:
    return {
        "accelerator": "gpu",
        "devices": 1,
        "enable_progress_bar": False,
        "enable_model_summary": False,
        "enable_checkpointing": False,
        "logger": False,
        "val_check_steps": MAX_STEPS,
    }


def common_kwargs() -> dict[str, Any]:
    return {
        "h": 1,
        "input_size": INPUT_SIZE,
        "max_steps": MAX_STEPS,
        "learning_rate": 1e-3,
        "random_seed": SEED,
        "loss": MAE(),
        "valid_loss": MAE(),
        "scaler_type": "standard",
        **trainer_kwargs(),
    }


def factories() -> list[
    tuple[str, Callable[[], Any]]
]:
    return [
        (
            "MLP",
            lambda: MLP(
                hidden_size=32,
                num_layers=1,
                alias="rolling_MLP",
                **common_kwargs(),
            ),
        ),
        (
            "NLinear",
            lambda: NLinear(
                alias="rolling_NLinear",
                **common_kwargs(),
            ),
        ),
        (
            "TCN",
            lambda: TCN(
                encoder_hidden_size=16,
                kernel_size=3,
                dilations=[1, 2],
                decoder_hidden_size=16,
                alias="rolling_TCN",
                **common_kwargs(),
            ),
        ),
        (
            "TimesNet",
            lambda: TimesNet(
                hidden_size=16,
                conv_hidden_size=16,
                encoder_layers=1,
                top_k=2,
                alias="rolling_TimesNet",
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
                alias="rolling_KAN",
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
                alias="rolling_Informer",
                **common_kwargs(),
            ),
        ),
    ]


def cleanup() -> None:
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def digitize(value: float) -> int:
    return int(
        np.clip(
            np.rint(value),
            0,
            9,
        )
    )


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = (
        pd.read_parquet(DATA_PATH)
        .sort_values("ds")
        .reset_index(drop=True)
    )

    df["original_ds"] = pd.to_datetime(df["ds"])
    df["ds"] = np.arange(len(df), dtype=int)
    df["y"] = df["y"].astype(float)
    df["unique_id"] = "N1"

    assert len(df) == 7039
    assert torch.cuda.is_available()

    torch.set_float32_matmul_precision("high")

    first_test_index = len(df) - ROLLING_POINTS

    rows: list[dict[str, Any]] = []

    for model_name, factory in factories():
        print()
        print(f"=== {model_name} ===")

        for test_index in range(
            first_test_index,
            len(df),
        ):
            cleanup()

            history = df.iloc[:test_index][
                ["unique_id", "ds", "y"]
            ].copy()

            actual_row = df.iloc[test_index]
            actual = float(actual_row["y"])

            try:
                torch.cuda.reset_peak_memory_stats()

                model = factory()

                nf = NeuralForecast(
                    models=[model],
                    freq=1,
                )

                fit_start = time.perf_counter()
                nf.fit(df=history)
                fit_seconds = (
                    time.perf_counter() - fit_start
                )

                predict_start = time.perf_counter()
                forecast = nf.predict()
                predict_seconds = (
                    time.perf_counter() - predict_start
                )

                columns = [
                    column
                    for column in forecast.columns
                    if column not in {"unique_id", "ds"}
                ]

                if len(columns) != 1:
                    raise RuntimeError(
                        f"Unexpected columns: {columns}"
                    )

                raw = float(
                    forecast[columns[0]].iloc[0]
                )

                if not np.isfinite(raw):
                    raise RuntimeError(
                        "Non-finite prediction"
                    )

                digit = digitize(raw)
                error = actual - raw
                digit_error = actual - digit

                row = {
                    "model": model_name,
                    "status": "PASS",
                    "test_index": int(test_index),
                    "original_ds": str(
                        actual_row["original_ds"]
                    ),
                    "actual": actual,
                    "prediction_raw": raw,
                    "prediction_digit": digit,
                    "raw_abs_error": abs(error),
                    "raw_squared_error": error**2,
                    "digit_abs_error": abs(
                        digit_error
                    ),
                    "digit_squared_error": (
                        digit_error**2
                    ),
                    "within_1": int(
                        abs(digit_error) <= 1
                    ),
                    "exact": int(
                        digit_error == 0
                    ),
                    "fit_seconds": fit_seconds,
                    "predict_seconds": (
                        predict_seconds
                    ),
                    "peak_vram_mib": (
                        torch.cuda
                        .max_memory_allocated()
                        / 1024**2
                    ),
                }

                rows.append(row)

                print(
                    model_name,
                    test_index,
                    f"actual={actual:.0f}",
                    f"pred={raw:.4f}",
                    f"digit={digit}",
                )

            except Exception as exc:
                rows.append(
                    {
                        "model": model_name,
                        "status": "FAIL",
                        "test_index": int(
                            test_index
                        ),
                        "original_ds": str(
                            actual_row["original_ds"]
                        ),
                        "actual": actual,
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
                    model_name,
                    test_index,
                    "FAIL",
                    type(exc).__name__,
                    str(exc),
                )

    detail = pd.DataFrame(rows)

    detail_path = (
        OUTPUT_DIR
        / "numbers3_n1_rolling_top6_detail.parquet"
    )

    detail.to_parquet(
        detail_path,
        index=False,
    )

    passed = detail[
        detail["status"] == "PASS"
    ].copy()

    summary = (
        passed.groupby("model")
        .agg(
            predictions=(
                "prediction_digit",
                "size",
            ),
            raw_mae=(
                "raw_abs_error",
                "mean",
            ),
            raw_mse=(
                "raw_squared_error",
                "mean",
            ),
            digit_mae=(
                "digit_abs_error",
                "mean",
            ),
            digit_mse=(
                "digit_squared_error",
                "mean",
            ),
            within_1_rate=(
                "within_1",
                "mean",
            ),
            exact_rate=(
                "exact",
                "mean",
            ),
            mean_fit_seconds=(
                "fit_seconds",
                "mean",
            ),
            total_fit_seconds=(
                "fit_seconds",
                "sum",
            ),
            mean_predict_seconds=(
                "predict_seconds",
                "mean",
            ),
            maximum_peak_vram_mib=(
                "peak_vram_mib",
                "max",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "digit_mae",
                "digit_mse",
                "within_1_rate",
            ],
            ascending=[
                True,
                True,
                False,
            ],
        )
    )

    summary["beats_mae_baseline"] = (
        summary["digit_mae"] < 2.56
    )

    summary["beats_within_1_baseline"] = (
        summary["within_1_rate"] > 0.325
    )

    summary["beats_exact_baseline"] = (
        summary["exact_rate"] > 0.17
    )

    summary_path = (
        OUTPUT_DIR
        / "numbers3_n1_rolling_top6_summary.csv"
    )

    summary.to_csv(
        summary_path,
        index=False,
    )

    json_path = (
        OUTPUT_DIR
        / "numbers3_n1_rolling_top6_summary.json"
    )

    json_path.write_text(
        json.dumps(
            summary.to_dict(
                orient="records"
            ),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("=== Rolling summary ===")
    print(
        summary.to_string(
            index=False,
            float_format=lambda x: f"{x:.6f}",
        )
    )

    failures = int(
        (detail["status"] == "FAIL").sum()
    )

    print()
    print("rows=", len(detail))
    print("failures=", failures)
    print("detail=", detail_path)
    print("summary=", summary_path)

    if failures:
        print(
            "NUMBERS3_N1_ROLLING_TOP6=PARTIAL"
        )
    else:
        print(
            "NUMBERS3_N1_ROLLING_TOP6=PASS"
        )


if __name__ == "__main__":
    main()
