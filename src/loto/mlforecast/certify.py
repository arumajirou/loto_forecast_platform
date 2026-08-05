from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import os
import platform
import sys
import traceback
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.mlforecast.artifacts import _write_manifest, atomic_write_text, sha256_file
from loto.mlforecast.contracts import AutoConfig, CoreConfig
from loto.mlforecast.factory import (
    auto_fit_kwargs,
    build_auto_forecast,
    build_core_forecast,
    core_fit_kwargs,
    hit_at_1_objective,
)
from loto.mlforecast.provenance import (
    MLFORECAST_REQUIRED_VERSION,
    MLFORECAST_WHEEL_SHA256,
    upstream_contract,
    verify_mlforecast_runtime,
)


@dataclass(frozen=True)
class CertificationResult:
    status: str
    run_id: str
    run_dir: Path
    report_path: Path


def verify_wheel_file(
    wheel_path: Path,
    *,
    expected_sha256: str = MLFORECAST_WHEEL_SHA256,
    expected_version: str = MLFORECAST_REQUIRED_VERSION,
) -> dict[str, Any]:
    """Verify the exact PyPI wheel bytes and embedded package metadata."""
    wheel_path = wheel_path.resolve()
    if not wheel_path.is_file():
        raise FileNotFoundError(f"MLForecast wheel not found: {wheel_path}")
    if wheel_path.suffix != ".whl":
        raise ValueError(f"expected a .whl file: {wheel_path}")

    actual_sha256 = sha256_file(wheel_path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "MLForecast wheel SHA-256 mismatch: "
            f"expected={expected_sha256}, actual={actual_sha256}"
        )

    with zipfile.ZipFile(wheel_path) as archive:
        metadata_paths = [
            name
            for name in archive.namelist()
            if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise RuntimeError(
                "MLForecast wheel must contain exactly one dist-info/METADATA file"
            )
        package_metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))

    package_name = package_metadata.get("Name")
    package_version = package_metadata.get("Version")
    if package_name != "mlforecast" or package_version != expected_version:
        raise RuntimeError(
            "MLForecast wheel metadata mismatch: "
            f"name={package_name!r}, version={package_version!r}"
        )
    return {
        "path": str(wheel_path),
        "filename": wheel_path.name,
        "size_bytes": wheel_path.stat().st_size,
        "sha256": actual_sha256,
        "metadata_name": package_name,
        "metadata_version": package_version,
        "verified": True,
    }


def _panel(rows: int = 48) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for series_index, unique_id in enumerate(("p1", "p2"), start=1):
        for ds in range(rows):
            value = float(series_index + (ds % 7) + (ds // 12) * 0.05)
            records.append({"unique_id": unique_id, "ds": ds, "y": value})
    return pd.DataFrame(records)


def _prediction_check(
    prediction: pd.DataFrame,
    *,
    column: str,
    expected_rows: int,
) -> dict[str, Any]:
    if prediction.shape[0] != expected_rows:
        raise RuntimeError(
            f"unexpected prediction rows for {column}: "
            f"expected={expected_rows}, actual={prediction.shape[0]}"
        )
    if column not in prediction.columns:
        raise RuntimeError(f"missing prediction column: {column}")
    values = prediction[column].to_numpy(dtype=float)
    finite = bool(np.isfinite(values).all())
    if not finite:
        raise RuntimeError(f"non-finite prediction values detected for {column}")
    return {
        "rows": int(prediction.shape[0]),
        "columns": list(prediction.columns),
        "prediction_column": column,
        "finite": finite,
        "minimum": float(values.min()),
        "maximum": float(values.max()),
    }


def _save_load_check(
    model: Any,
    prediction: pd.DataFrame,
    *,
    model_dir: Path,
    column: str,
) -> dict[str, Any]:
    from mlforecast import MLForecast

    model_dir.mkdir(parents=True, exist_ok=False)
    model.save(str(model_dir))
    loaded = MLForecast.load(str(model_dir))
    repeated = loaded.predict(h=1)
    _prediction_check(repeated, column=column, expected_rows=prediction.shape[0])
    before = prediction.sort_values(["unique_id", "ds"])[column].to_numpy(float)
    after = repeated.sort_values(["unique_id", "ds"])[column].to_numpy(float)
    match = bool(np.allclose(before, after, rtol=1e-8, atol=1e-8))
    if not match:
        raise RuntimeError(f"save/load prediction mismatch for {column}")
    return {
        "path": str(model_dir),
        "prediction_match": match,
        "rtol": 1e-8,
        "atol": 1e-8,
    }


def _core_certification(run_dir: Path, panel: pd.DataFrame, *, seed: int) -> dict[str, Any]:
    config = CoreConfig(
        models=["ridge"],
        lags=[1, 2, 7],
        cv_n_windows=2,
        num_threads=1,
        cache_train_df=True,
    )
    model = build_core_forecast(config, seed=seed)
    model.fit(panel, static_features=[], **core_fit_kwargs(config))
    prediction = model.predict(h=1)
    prediction.to_csv(run_dir / "core_ridge_predictions.csv", index=False)
    check = _prediction_check(prediction, column="ridge", expected_rows=2)
    saved = _save_load_check(
        model,
        prediction,
        model_dir=run_dir / "models" / "core-ridge",
        column="ridge",
    )
    estimator = model.models_["ridge"]
    return {
        "status": "PASS",
        "estimator": f"{type(estimator).__module__}.{type(estimator).__name__}",
        "prediction": check,
        "save_load": saved,
    }


def _auto_certification(
    run_dir: Path,
    panel: pd.DataFrame,
    *,
    seed: int,
    trials: int,
) -> dict[str, Any]:
    config = AutoConfig(
        models=["AutoRidge"],
        season_length=1,
        n_windows=2,
        num_samples=trials,
        sampler="tpe",
        num_threads=1,
        n_jobs=1,
        cache_train_df=True,
    )
    model = build_auto_forecast(config, static_features=[])
    kwargs = auto_fit_kwargs(config, seed=seed)
    kwargs["h"] = 1
    model.fit(
        panel,
        loss=lambda validation, train_df, weight_col=None: hit_at_1_objective(
            validation,
            train_df,
            weight_col=weight_col,
        ),
        **{key: value for key, value in kwargs.items() if value is not None},
    )
    prediction = model.predict(h=1)
    prediction.to_csv(run_dir / "auto_ridge_predictions.csv", index=False)
    check = _prediction_check(prediction, column="AutoRidge", expected_rows=2)

    study = model.results_["AutoRidge"]
    trial_frame = study.trials_dataframe()
    trial_frame.to_csv(run_dir / "auto_ridge_trials.csv", index=False)
    complete_trials = sum(trial.state.name == "COMPLETE" for trial in study.trials)
    if len(study.trials) != trials or complete_trials < 1:
        raise RuntimeError(
            "AutoRidge trial contract failed: "
            f"requested={trials}, observed={len(study.trials)}, complete={complete_trials}"
        )

    fitted = model.models_["AutoRidge"]
    saved = _save_load_check(
        fitted,
        prediction,
        model_dir=run_dir / "models" / "auto-ridge",
        column="AutoRidge",
    )
    estimator = fitted.models_["AutoRidge"]
    return {
        "status": "PASS",
        "estimator": f"{type(estimator).__module__}.{type(estimator).__name__}",
        "sampler": type(study.sampler).__name__,
        "requested_trials": trials,
        "observed_trials": len(study.trials),
        "complete_trials": complete_trials,
        "best_value": float(study.best_value),
        "prediction": check,
        "save_load": saved,
    }


def _runtime_environment() -> dict[str, Any]:
    packages = {}
    for package in (
        "mlforecast",
        "coreforecast",
        "utilsforecast",
        "optuna",
        "scikit-learn",
        "numpy",
        "pandas",
    ):
        try:
            packages[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            packages[package] = None
    affinity = None
    if hasattr(os, "sched_getaffinity"):
        affinity = len(os.sched_getaffinity(0))
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "cpu_count": os.cpu_count(),
        "cpu_affinity_count": affinity,
        "device": "cpu",
        "gpu_required": False,
        "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
        "thread_environment": {
            name: os.getenv(name)
            for name in (
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "packages": packages,
    }


def run_certification(
    *,
    wheel_path: Path,
    output_root: Path,
    seed: int = 1,
    auto_trials: int = 2,
) -> CertificationResult:
    if auto_trials < 1:
        raise ValueError("auto_trials must be positive")
    run_id = datetime.now(UTC).strftime("mlforecast-runtime-%Y%m%d-%H%M%S-%f")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = run_dir / "RUNTIME_CERTIFICATION.json"
    report: dict[str, Any] = {
        "status": "RUNNING",
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "auto_trials": auto_trials,
        "upstream": upstream_contract(),
    }
    try:
        report["wheel"] = verify_wheel_file(wheel_path)
        report["runtime"] = verify_mlforecast_runtime()
        report["environment"] = _runtime_environment()
        panel = _panel()
        panel.to_csv(run_dir / "synthetic_panel.csv", index=False)
        report["input"] = {
            "rows": int(panel.shape[0]),
            "series": int(panel["unique_id"].nunique()),
            "finite_target": bool(np.isfinite(panel["y"].to_numpy(float)).all()),
        }
        report["core_ridge"] = _core_certification(run_dir, panel, seed=seed)
        report["auto_ridge"] = _auto_certification(
            run_dir,
            panel,
            seed=seed,
            trials=auto_trials,
        )
        report["status"] = "RUNTIME_CERTIFIED"
    except Exception as exc:  # noqa: BLE001 - certification must persist failure evidence
        report["status"] = "FAILED"
        report["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    report["finished_at"] = datetime.now(UTC).isoformat()
    atomic_write_text(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write_manifest(run_dir)
    return CertificationResult(
        status=str(report["status"]),
        run_id=run_id,
        run_dir=run_dir,
        report_path=report_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loto-mlforecast-certify",
        description="Certify the frozen MLForecast wheel and Core/Auto runtime lifecycle",
    )
    parser.add_argument("--wheel", type=Path, required=True, help="Official MLForecast wheel")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/mlforecast-runtime-certification"),
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--auto-trials", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_certification(
        wheel_path=args.wheel,
        output_root=args.output_root,
        seed=args.seed,
        auto_trials=args.auto_trials,
    )
    print(
        json.dumps(
            {
                "status": result.status,
                "run_id": result.run_id,
                "run_dir": str(result.run_dir),
                "report": str(result.report_path),
            },
            sort_keys=True,
        )
    )
    return 0 if result.status == "RUNTIME_CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
