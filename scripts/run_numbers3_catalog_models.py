from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import signal
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.models.catalog import MODEL_SPECS, get_model_spec
from loto.models.workers import PositionSeriesWorker, WorkerOutput

DIGITS = ("d1", "d2", "d3")
CANONICAL_POSITIONS = ("n1", "n2", "n3")


class GracefulStop(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Leakage-safe Numbers3 catalog-model backtest, save and reload validation"
    )
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--models", default="all")
    parser.add_argument("--test-draws", type=int, default=30)
    parser.add_argument("--min-train-draws", type=int, default=1000)
    parser.add_argument("--lags", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--num-samples", type=int, default=5)
    parser.add_argument("--hpo-backend", choices=("optuna", "ray"), default="optuna")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--precision", default="32")
    parser.add_argument("--save-models", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reload-models", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--verify-reload-predictions", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--timeout-per-model", type=int, default=7200)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_numbers3(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    required = {"draw_no", "draw_date", *DIGITS}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    frame = frame.copy()
    frame["draw_date"] = pd.to_datetime(frame["draw_date"], errors="raise")
    frame["draw_no"] = pd.to_numeric(frame["draw_no"], errors="raise").astype(int)
    for column in DIGITS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(int)
        if not frame[column].between(0, 9).all():
            raise ValueError(f"{column} contains values outside 0..9")
    frame = frame.sort_values(["draw_no", "draw_date"]).drop_duplicates("draw_no", keep="last")
    frame = frame.reset_index(drop=True)
    if not frame["draw_no"].is_monotonic_increasing:
        raise ValueError("draw_no is not monotonic increasing")
    return frame


def to_worker_history(frame: pd.DataFrame) -> pd.DataFrame:
    history = frame[["draw_no", "draw_date", *DIGITS]].rename(
        columns=dict(zip(DIGITS, CANONICAL_POSITIONS, strict=True))
    )
    return history.reset_index(drop=True)


def requested_model_ids(value: str) -> list[str]:
    if value.strip().lower() == "all":
        return [spec.model_id for spec in MODEL_SPECS]
    ids = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [
        model_id for model_id in ids if model_id not in {spec.model_id for spec in MODEL_SPECS}
    ]
    if unknown:
        raise ValueError(f"unknown model ids: {unknown}")
    return list(dict.fromkeys(ids))


def model_params(model_id: str, args: argparse.Namespace) -> dict[str, Any]:
    spec = get_model_spec(model_id)
    params: dict[str, Any] = {}
    if spec.library in {"sklearn", "lightgbm", "mlforecast"}:
        params["lags"] = list(range(1, min(args.lags, 20) + 1))
    if spec.library == "neuralforecast":
        params.update(max_steps=args.max_steps, val_check_steps=max(1, min(50, args.max_steps)))
    if spec.library == "neuralforecast_auto":
        params.update(
            backend=args.hpo_backend,
            num_samples=args.num_samples,
            parallel_trials=1,
            max_steps=args.max_steps,
        )
    return params


def predict_worker(
    model_id: str, history: pd.DataFrame, args: argparse.Namespace, seed: int
) -> WorkerOutput:
    spec = get_model_spec(model_id)
    if spec.task in {"candidate", "candidate_series"}:
        raise NotImplementedError(
            "candidate-space models are Loto7-specific and cannot be "
            "truthfully mapped to Numbers3 digits"
        )
    worker = PositionSeriesWorker(
        spec,
        model_params(model_id, args),
        seed=seed,
        device=args.device,
        precision=args.precision,
        position_columns=list(CANONICAL_POSITIONS),
    )
    output = worker.forecast(history)
    values = np.asarray(output.position_values, dtype=float).reshape(-1)
    if values.shape != (3,):
        raise ValueError(f"Numbers3 prediction must contain 3 values, got {values.shape}")
    if not np.isfinite(values).all():
        raise ValueError("prediction contains NaN or Inf")
    output.position_values = np.clip(np.rint(values), 0, 9).astype(int)
    return output


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    actual = frame[[f"actual_{d}" for d in DIGITS]].to_numpy(float)
    predicted = frame[[f"pred_{d}" for d in DIGITS]].to_numpy(float)
    error = np.abs(actual - predicted)
    return {
        "folds": len(frame),
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_payload(output: WorkerOutput, directory: Path) -> tuple[Path | None, str]:
    directory.mkdir(parents=True, exist_ok=True)
    payload = output.model_artifact_payload
    if payload is None:
        return None, "ARTIFACT_NOT_EXPOSED_BY_PROVIDER"
    path = directory / "model.pkl"
    try:
        with path.open("wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        path.unlink(missing_ok=True)
        return None, f"SERIALIZATION_FAILED:{type(exc).__name__}:{exc}"
    return path, "OK"


def reload_payload(path: Path) -> Any:
    with path.open("rb") as handle:
        return pickle.load(handle)


def replay_payload(payload: dict[str, Any], history: pd.DataFrame) -> np.ndarray | None:
    library = payload.get("library")
    if library == "lag_regression":
        values = []
        for estimator, fallback in zip(
            payload["estimators"], payload["fallback_values"], strict=True
        ):
            if estimator is None:
                values.append(float(fallback))
                continue
            series_index = len(values) + 1
            series = history[f"n{series_index}"].astype(float).to_numpy()
            query = np.asarray([[series[-lag] for lag in payload["lags"]]])
            values.append(float(estimator.predict(query)[0]))
        return np.clip(np.rint(values), 0, 9).astype(int)
    if library == "statsforecast":
        prediction = payload["statsforecast"].predict(h=1)
        values = prediction.sort_values("unique_id")[payload["value_col"]].to_numpy(float)
        return np.clip(np.rint(values), 0, 9).astype(int)
    if library == "mlforecast":
        prediction = payload["mlforecast"].predict(1)
        values = prediction.sort_values("unique_id")[payload["value_col"]].to_numpy(float)
        return np.clip(np.rint(values), 0, 9).astype(int)
    return None


def atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    frame = load_numbers3(args.data)
    model_ids = requested_model_ids(args.models)
    if args.test_draws < 1 or len(frame) <= args.min_train_draws:
        raise ValueError("insufficient data or invalid test-draws")
    test_start = max(args.min_train_draws, len(frame) - args.test_draws)
    test_indices = list(range(test_start, len(frame)))
    if not test_indices:
        raise ValueError("no valid backtest folds")

    stop_requested = False

    def _stop(_signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    run_config = vars(args).copy()
    run_config.update(models=model_ids, rows=len(frame), test_indices=test_indices)
    run_config = {
        key: str(value) if isinstance(value, Path) else value for key, value in run_config.items()
    }
    atomic_json(args.output / "run_config.json", run_config)

    summaries: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    next_predictions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for model_id in model_ids:
        if stop_requested:
            break
        started = time.perf_counter()
        model_rows: list[dict[str, Any]] = []
        status = "OK"
        try:
            for fold, index in enumerate(test_indices, start=1):
                if stop_requested:
                    raise GracefulStop("stop requested")
                history = to_worker_history(frame.iloc[:index])
                output = predict_worker(model_id, history, args, args.seed + fold)
                values = output.position_values.astype(int)
                row = {
                    "model_id": model_id,
                    "fold": fold,
                    "draw_no": int(frame.iloc[index]["draw_no"]),
                    "draw_date": str(frame.iloc[index]["draw_date"].date()),
                }
                for offset, digit in enumerate(DIGITS):
                    row[f"actual_{digit}"] = int(frame.iloc[index][digit])
                    row[f"pred_{digit}"] = int(values[offset])
                model_rows.append(row)
                predictions.append(row)
            summary = evaluate(model_rows)

            full_history = to_worker_history(frame)
            final_output = predict_worker(model_id, full_history, args, args.seed)
            final_values = final_output.position_values.astype(int)
            model_dir = args.output / "models" / model_id
            artifact_path = None
            save_status = "DISABLED"
            reload_status = "DISABLED"
            parity_max_abs_diff = None
            if args.save_models:
                artifact_path, save_status = save_payload(final_output, model_dir)
            if args.reload_models and artifact_path is not None:
                loaded = reload_payload(artifact_path)
                replay = replay_payload(loaded, full_history)
                if replay is None:
                    reload_status = "DESERIALIZED_ONLY"
                else:
                    parity_max_abs_diff = float(np.max(np.abs(final_values - replay)))
                    reload_status = (
                        "OK"
                        if (not args.verify_reload_predictions or parity_max_abs_diff == 0.0)
                        else "MISMATCH"
                    )
                    if reload_status == "MISMATCH":
                        raise ValueError(f"reloaded prediction mismatch: {parity_max_abs_diff}")
            manifest = {
                "schema_version": 1,
                "model_id": model_id,
                "library": get_model_spec(model_id).library,
                "task": get_model_spec(model_id).task,
                "position_columns": list(CANONICAL_POSITIONS),
                "artifact": None if artifact_path is None else str(artifact_path),
                "artifact_sha256": None if artifact_path is None else sha256_file(artifact_path),
                "save_status": save_status,
                "reload_status": reload_status,
                "reload_prediction_max_abs_diff": parity_max_abs_diff,
                "metadata": final_output.metadata,
            }
            model_dir.mkdir(parents=True, exist_ok=True)
            atomic_json(model_dir / "model_manifest.json", manifest)
            atomic_json(model_dir / "metrics.json", summary)
            (model_dir / "SHA256SUMS").write_text(
                "".join(
                    f"{sha256_file(path)}  {path.name}\n"
                    for path in sorted(model_dir.iterdir())
                    if path.is_file() and path.name != "SHA256SUMS"
                ),
                encoding="utf-8",
            )
            next_row = {"model_id": model_id, "next_draw_no": int(frame.iloc[-1]["draw_no"]) + 1}
            for offset, digit in enumerate(DIGITS):
                next_row[f"pred_{digit}"] = int(final_values[offset])
            next_row["prediction"] = "".join(str(int(value)) for value in final_values)
            next_predictions.append(next_row)
            summary.update(
                model_id=model_id,
                status=status,
                duration_seconds=time.perf_counter() - started,
                save_status=save_status,
                reload_status=reload_status,
            )
            summaries.append(summary)
        except GracefulStop as exc:
            status = "INTERRUPTED"
            errors.append(
                {
                    "model_id": model_id,
                    "stage": "execution",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            summaries.append(
                {
                    "model_id": model_id,
                    "status": status,
                    "duration_seconds": time.perf_counter() - started,
                }
            )
            break
        except Exception as exc:
            status = "ERROR"
            errors.append(
                {
                    "model_id": model_id,
                    "stage": "execution",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            summaries.append(
                {
                    "model_id": model_id,
                    "status": status,
                    "duration_seconds": time.perf_counter() - started,
                    "error": str(exc),
                }
            )
        finally:
            pd.DataFrame(summaries).to_csv(args.output / "summary.csv", index=False)
            pd.DataFrame(predictions).to_csv(args.output / "predictions.csv", index=False)
            pd.DataFrame(next_predictions).to_csv(args.output / "next_predictions.csv", index=False)
            pd.DataFrame(errors, columns=["model_id", "stage", "error_type", "message"]).to_csv(
                args.output / "errors.csv", index=False
            )

    print(pd.DataFrame(summaries).to_string(index=False))
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
