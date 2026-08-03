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
    BiTCN,
    DilatedRNN,
    GRU,
    LSTM,
    RNN,
    TCN,
    TFT,
    TiDE,
    TimesNet,
    VanillaTransformer,
)


ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data" / "exports" / "numbers3" / "splits" / "n1_holdout200_ordinal"

OUTPUT_DIR = ROOT / "artifacts" / "numbers3" / "n1_nf_phase2"

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
        "loss": MAE(),
        "valid_loss": MAE(),
        "scaler_type": "standard",
        **trainer_kwargs(),
    }


def model_factories() -> list[tuple[str, Callable[[], Any]]]:
    return [
        (
            "RNN",
            lambda: RNN(
                encoder_hidden_size=16,
                encoder_n_layers=1,
                decoder_hidden_size=16,
                alias="numbers3_RNN",
                **common_kwargs(),
            ),
        ),
        (
            "GRU",
            lambda: GRU(
                encoder_hidden_size=16,
                encoder_n_layers=1,
                decoder_hidden_size=16,
                alias="numbers3_GRU",
                **common_kwargs(),
            ),
        ),
        (
            "LSTM",
            lambda: LSTM(
                encoder_hidden_size=16,
                encoder_n_layers=1,
                decoder_hidden_size=16,
                alias="numbers3_LSTM",
                **common_kwargs(),
            ),
        ),
        (
            "DilatedRNN",
            lambda: DilatedRNN(
                encoder_hidden_size=16,
                dilations=[[1, 2]],
                decoder_hidden_size=16,
                alias="numbers3_DilatedRNN",
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
                alias="numbers3_TCN",
                **common_kwargs(),
            ),
        ),
        (
            "BiTCN",
            lambda: BiTCN(
                hidden_size=16,
                dropout=0.0,
                alias="numbers3_BiTCN",
                **common_kwargs(),
            ),
        ),
        (
            "TiDE",
            lambda: TiDE(
                hidden_size=32,
                decoder_output_dim=8,
                num_encoder_layers=1,
                num_decoder_layers=1,
                temporal_decoder_dim=8,
                dropout=0.0,
                alias="numbers3_TiDE",
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
                alias="numbers3_TimesNet",
                **common_kwargs(),
            ),
        ),
        (
            "TFT",
            lambda: TFT(
                hidden_size=16,
                n_head=4,
                dropout=0.0,
                alias="numbers3_TFT",
                **common_kwargs(),
            ),
        ),
        (
            "VanillaTransformer",
            lambda: VanillaTransformer(
                hidden_size=16,
                n_head=4,
                encoder_layers=1,
                decoder_layers=1,
                dropout=0.0,
                alias="numbers3_VanillaTransformer",
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
        "raw_mae": float(np.mean(np.abs(raw_error))),
        "raw_mse": float(np.mean(raw_error**2)),
        "raw_rmse": float(np.sqrt(np.mean(raw_error**2))),
        "digit_mae": float(np.mean(np.abs(digit_error))),
        "digit_mse": float(np.mean(digit_error**2)),
        "digit_rmse": float(np.sqrt(np.mean(digit_error**2))),
        "within_1_rate": float(np.mean(np.abs(digit_error) <= 1)),
        "exact_rate": float(np.mean(digit_error == 0)),
        "prediction_min": float(raw.min()),
        "prediction_max": float(raw.max()),
        "prediction_mean": float(raw.mean()),
        "digit_prediction_mean": float(digit.mean()),
        "fit_seconds": float(fit_seconds),
        "predict_seconds": float(predict_seconds),
        "peak_vram_mib": float(peak_vram_mib),
        "beats_digit_mae_baseline": bool(np.mean(np.abs(digit_error)) < 2.56),
        "beats_within_1_baseline": bool(np.mean(np.abs(digit_error) <= 1) > 0.325),
        "beats_exact_baseline": bool(np.mean(digit_error == 0) > 0.17),
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

    train = pd.read_parquet(DATA_DIR / "train.parquet").sort_values("ds").reset_index(drop=True)

    test = pd.read_parquet(DATA_DIR / "test.parquet").sort_values("ds").reset_index(drop=True)

    train = train[["unique_id", "ds", "y"]].copy()

    train["unique_id"] = train["unique_id"].astype(str)
    train["ds"] = train["ds"].astype(int)
    train["y"] = train["y"].astype(float)

    actual = test["y"].to_numpy(dtype=float)

    assert len(train) == 6839
    assert len(test) == 200
    assert torch.cuda.is_available()

    torch.set_float32_matmul_precision("high")

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
            fit_seconds = time.perf_counter() - fit_started

            predict_started = time.perf_counter()
            forecast = nf.predict()
            predict_seconds = time.perf_counter() - predict_started

            columns = [column for column in forecast.columns if column not in {"unique_id", "ds"}]

            if len(columns) != 1:
                raise RuntimeError(f"Unexpected forecast columns: {columns}")

            forecast_column = columns[0]

            raw = forecast[forecast_column].to_numpy(dtype=float)

            if len(raw) != len(actual):
                raise RuntimeError(f"Prediction length={len(raw)}, expected={len(actual)}")

            if not np.isfinite(raw).all():
                raise RuntimeError("Non-finite predictions detected")

            peak_vram_mib = torch.cuda.max_memory_allocated() / 1024**2

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
                        "original_ds": test["original_ds"].to_numpy(),
                        "actual": actual,
                        "prediction_raw": raw,
                        "prediction_digit": (digitize(raw)),
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
                    "error_type": (type(exc).__name__),
                    "error": str(exc),
                    "traceback": (traceback.format_exc()),
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

    csv_output = OUTPUT_DIR / "numbers3_n1_nf_phase2_results.csv"

    json_output = OUTPUT_DIR / "numbers3_n1_nf_phase2_results.json"

    predictions_output = OUTPUT_DIR / "numbers3_n1_nf_phase2_predictions.parquet"

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
    print("=== Phase 2 results ===")
    print(
        results[display_columns].to_string(
            index=False,
            float_format=(lambda value: f"{value:.6f}"),
        )
    )

    passed = int((results["status"] == "PASS").sum())
    failed = int((results["status"] == "FAIL").sum())

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
        print("NUMBERS3_N1_NF_PHASE2=PARTIAL")
    else:
        print("NUMBERS3_N1_NF_PHASE2=PASS")


if __name__ == "__main__":
    main()
