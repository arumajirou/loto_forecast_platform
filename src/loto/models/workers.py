from __future__ import annotations

# ruff: noqa: E501
import hashlib
import importlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.models.catalog import ModelSpec
from loto.models.neuralforecast_adapter import (
    AutoModelRequest,
    construct_auto_model,
    resolve_auto_model_plan,
)
from loto.models.providers import FoundationProviderError, get_foundation_provider

ROOT = Path(__file__).resolve().parents[3]
AUTOGLUON_ENV = ROOT / "environments" / "autogluon-timeseries"
AUTOGLUON_RUNNER = ROOT / "scripts" / "run_autogluon_timeseries_provider.py"


class WorkerSubprocessError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class WorkerOutput:
    position_values: np.ndarray
    metadata: dict[str, Any]
    candidate_probabilities: np.ndarray | None = None
    model_artifact_payload: Any | None = None


def infer_position_columns(frame: pd.DataFrame) -> list[str]:
    """Return canonical position columns in numeric order.

    The original runtime was Loto7-only (n1..n7).  Numbers3 and other games use
    fewer independent position series, so workers must derive the contract from
    the supplied frame instead of silently fabricating missing positions.
    """
    columns = [
        column for column in frame.columns if column.startswith("n") and column[1:].isdigit()
    ]
    return sorted(columns, key=lambda value: int(value[1:]))


def canonical_to_long(
    master: pd.DataFrame,
    position_columns: list[str] | None = None,
) -> pd.DataFrame:
    columns = position_columns or infer_position_columns(master)
    if not columns:
        raise ValueError("no canonical position columns found")
    records: list[dict[str, Any]] = []
    for row in master.itertuples(index=False):
        for index, column in enumerate(columns, start=1):
            records.append(
                {
                    "unique_id": f"position-{index}",
                    "ds": pd.Timestamp(row.draw_date),
                    "y": float(getattr(row, column)),
                }
            )
    return pd.DataFrame(records).sort_values(["unique_id", "ds"]).reset_index(drop=True)


def autohint_hierarchy_frame(history: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    series_order = ["total", *[f"position-{position}" for position in range(1, 8)]]
    bottom_series_order = [f"position-{position}" for position in range(1, 8)]
    internal_series_order = [
        "00-total",
        *[f"{position:02d}-position-{position}" for position in range(1, 8)],
    ]
    internal_bottom_series_order = [
        f"{position:02d}-position-{position}" for position in range(1, 8)
    ]
    internal_to_external = dict(zip(internal_series_order, series_order, strict=True))
    rows: list[dict[str, Any]] = []
    for row in history.itertuples(index=False):
        values = np.asarray([float(getattr(row, f"n{i}")) for i in range(1, 8)])
        ds = pd.Timestamp(row.draw_date)
        rows.append({"unique_id": "00-total", "ds": ds, "y": float(values.sum())})
        for position, value in enumerate(values, start=1):
            rows.append(
                {"unique_id": f"{position:02d}-position-{position}", "ds": ds, "y": float(value)}
            )
    frame = pd.DataFrame(rows).sort_values(["unique_id", "ds"]).reset_index(drop=True)
    s_matrix = np.vstack([np.ones(7, dtype=np.float32), np.eye(7, dtype=np.float32)])
    validation = {
        "shape": list(s_matrix.shape),
        "rank": int(np.linalg.matrix_rank(s_matrix)),
        "top_row": s_matrix[0].astype(int).tolist(),
        "mathematically_valid_hierarchy": True,
        "domain_semantic_strength": "weak",
        "runtime_validation_purpose": "contract_and_execution",
    }
    totals = frame[frame["unique_id"] == "00-total"].sort_values("ds")["y"].to_numpy(float)
    bottom = [
        frame[frame["unique_id"] == unique_id].sort_values("ds")["y"].to_numpy(float)
        for unique_id in internal_bottom_series_order
    ]
    validation["top_equals_bottom_sum"] = bool(np.allclose(totals, np.sum(bottom, axis=0)))
    matrix_hash = hashlib.sha256(np.ascontiguousarray(s_matrix).tobytes()).hexdigest()
    return frame, {
        "hierarchy_definition": {
            "kind": "total_plus_positions",
            "tree": {"total": bottom_series_order},
            "notes": "Loto7 position-value sum is mathematically additive but weak semantically.",
        },
        "summation_matrix": s_matrix,
        "summation_matrix_sha256": matrix_hash,
        "series_order": series_order,
        "bottom_series_order": bottom_series_order,
        "internal_series_order": internal_series_order,
        "internal_bottom_series_order": internal_bottom_series_order,
        "internal_to_external": internal_to_external,
        "hierarchy_validation": validation,
    }


def _robust_position_sigma(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(float)
    if len(values) < 3:
        return 2.0
    diff = np.diff(values)
    median = float(np.median(diff))
    mad = float(np.median(np.abs(diff - median)))
    sigma = 1.4826 * mad
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = float(np.std(diff)) if len(diff) > 1 else 2.0
    return float(np.clip(sigma, 0.75, 6.0))


def position_values_to_candidate_probabilities(
    history: pd.DataFrame, values: np.ndarray
) -> np.ndarray:
    """Convert seven model position forecasts into marginal selection probabilities.

    Each position is represented as a discrete Gaussian whose spread is estimated
    only from historical first differences. Combining the position distributions
    yields candidate inclusion probabilities derived from the model output instead
    of the former uniform placeholder.
    """
    centers = np.asarray(values, dtype=float).reshape(7)
    candidates = np.arange(1, 38, dtype=float)
    per_position: list[np.ndarray] = []
    for index, center in enumerate(centers, start=1):
        sigma = _robust_position_sigma(history[f"n{index}"])
        weights = np.exp(-0.5 * ((candidates - center) / sigma) ** 2)
        weights /= max(float(weights.sum()), 1e-12)
        per_position.append(weights)
    matrix = np.vstack(per_position)
    inclusion = 1.0 - np.prod(1.0 - matrix, axis=0)
    # Legal Loto7 marginal probabilities should sum to approximately seven.
    result = np.clip(inclusion, 1e-9, 1.0 - 1e-9)
    for _ in range(20):
        current = float(result.sum())
        if abs(current - 7.0) < 1e-8 or current <= 0:
            break
        result = np.clip(result * (7.0 / current), 1e-9, 1.0 - 1e-9)
    return result


def normalize_worker_predictions(
    *,
    task: str,
    history: pd.DataFrame,
    values: np.ndarray | list[float],
) -> np.ndarray:
    """Normalize worker predictions into the 37-candidate marginal contract."""
    if task in {"position", "position_series"}:
        raw = np.asarray(values, dtype=float).reshape(-1)
        if raw.size != 7:
            raise ValueError(f"{task} model must return 7 values, got {raw.size}")
        if not np.isfinite(raw).all():
            raise ValueError(f"{task} predictions contain NaN or Inf")
        return position_values_to_candidate_probabilities(history, raw)

    if task in {"candidate", "candidate_series"}:
        scores = np.asarray(values, dtype=float).reshape(-1)
        if scores.size != 37:
            raise ValueError(f"{task} model must return 37 values, got {scores.size}")
        if not np.isfinite(scores).all():
            raise ValueError(f"{task} predictions contain NaN or Inf")
        scores = np.clip(scores, 0.0, None)
        total = float(scores.sum())
        if total <= 0:
            return np.full(37, 7.0 / 37.0, dtype=float)
        return scores * (7.0 / total)

    raise ValueError(f"unsupported worker prediction task: {task}")


class PositionSeriesWorker:
    """Execute optional time-series libraries behind a stable contract."""

    def __init__(
        self,
        spec: ModelSpec,
        params: dict[str, Any] | None = None,
        *,
        seed: int = 42,
        device: str = "auto",
        precision: str = "32",
        position_columns: list[str] | None = None,
    ):
        self.spec = spec
        self.params = spec.default_params | (params or {})
        self.seed = seed
        self.device = device
        self.precision = precision
        self.position_columns = position_columns

    def _columns(self, history: pd.DataFrame) -> list[str]:
        columns = self.position_columns or infer_position_columns(history)
        if not columns:
            raise ValueError("no position columns available for worker")
        missing = [column for column in columns if column not in history.columns]
        if missing:
            raise ValueError(f"history is missing position columns: {missing}")
        return columns

    def forecast(self, history: pd.DataFrame) -> WorkerOutput:
        if self.spec.library in {"sklearn", "lightgbm"}:
            output = self._lag_regression(history)
        elif getattr(self.spec, "task", None) == "candidate_series":
            output = self._candidate_series(history)
        elif self.spec.library == "statsforecast":
            output = self._statsforecast(history)
        elif self.spec.library == "mlforecast":
            output = self._mlforecast(history)
        elif self.spec.library == "neuralforecast":
            output = self._neuralforecast(history)
        elif self.spec.library == "neuralforecast_auto":
            if self.spec.class_name == "AutoHINT":
                output = self._autohint(history)
            else:
                output = self._neuralforecast_auto(history)
        elif self.spec.library == "autogluon":
            output = self._autogluon(history)
        elif self.spec.library == "darts":
            output = self._darts(history)
        elif self.spec.library == "gluonts":
            output = self._gluonts(history)
        elif self.spec.library == "reservoirpy":
            output = self._reservoir_esn(history)
        elif self.spec.library in {"chronos", "timesfm", "transformers", "tirex", "uni2ts"}:
            output = self._foundation(history)
        else:
            raise NotImplementedError(f"no position worker for library={self.spec.library}")
        if output.candidate_probabilities is None and len(self._columns(history)) == 7:
            output.candidate_probabilities = normalize_worker_predictions(
                task=getattr(self.spec, "task", "position_series"),
                history=history,
                values=output.position_values,
            )
        return output

    def _candidate_series_frame(self, history: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for row in history.itertuples(index=False):
            selected = {int(getattr(row, f"n{i}")) for i in range(1, 8)}
            for candidate in range(1, 38):
                rows.append(
                    {
                        "unique_id": f"candidate-{candidate:02d}",
                        "ds": pd.Timestamp(row.draw_date),
                        "y": float(candidate in selected),
                    }
                )
        return pd.DataFrame(rows).sort_values(["unique_id", "ds"]).reset_index(drop=True)

    def _candidate_series(self, history: pd.DataFrame) -> WorkerOutput:
        if self.spec.library != "statsforecast":
            raise RuntimeError(
                f"candidate_series worker is not implemented for library={self.spec.library}"
            )
        from statsforecast import StatsForecast

        models_module = importlib.import_module("statsforecast.models")
        cls = getattr(models_module, self.spec.class_name)
        params = dict(self.params)
        if self.spec.class_name == "TSB":
            params.setdefault("alpha_d", 0.3)
            params.setdefault("alpha_p", 0.3)
        model = cls(**params)
        frame = self._candidate_series_frame(history)
        sf = StatsForecast(models=[model], freq="7D", n_jobs=1)
        sf.fit(df=frame)
        prediction = sf.predict(h=1)
        value_col = [c for c in prediction.columns if c not in {"unique_id", "ds"}][0]
        scored = prediction.sort_values("unique_id")[value_col].to_numpy(float)
        probabilities = normalize_worker_predictions(
            task=self.spec.task,
            history=history,
            values=scored,
        )
        ranked = np.argsort(-probabilities)[:7] + 1
        values = np.asarray(sorted(ranked.tolist()), dtype=float)
        return WorkerOutput(
            values,
            {
                "library": "statsforecast",
                "task": "candidate_series",
                "column": value_col,
                "params": params,
            },
            probabilities,
            {"library": "statsforecast", "statsforecast": sf, "value_col": value_col},
        )

    def _lag_regression(self, history: pd.DataFrame) -> WorkerOutput:
        lags = list(self.params.get("lags", [1, 2, 3, 5, 10, 20]))
        lags = sorted({int(lag) for lag in lags if int(lag) > 0})
        fit_params = {k: v for k, v in self.params.items() if k != "lags"}
        values: list[float] = []
        estimators: list[Any] = []
        for position, column in enumerate(self._columns(history), start=1):
            series = history[column].astype(float).to_numpy()
            max_lag = max(lags)
            if len(series) <= max_lag + 2:
                values.append(float(np.median(series)))
                estimators.append(None)
                continue
            x = np.asarray([[series[t - lag] for lag in lags] for t in range(max_lag, len(series))])
            y = series[max_lag:]
            query = np.asarray([[series[-lag] for lag in lags]])
            if self.spec.library == "lightgbm":
                from lightgbm import LGBMRegressor

                estimator = LGBMRegressor(random_state=self.seed, verbosity=-1, **fit_params)
            elif self.spec.class_name == "ElasticNet":
                from sklearn.linear_model import ElasticNet

                estimator = ElasticNet(**fit_params)
            else:
                from sklearn.linear_model import Ridge

                estimator = Ridge(**fit_params)
            estimator.fit(x, y)
            estimators.append(estimator)
            values.append(float(estimator.predict(query)[0]))
        return WorkerOutput(
            np.asarray(values),
            {"library": self.spec.library, "lags": lags},
            model_artifact_payload={
                "library": "lag_regression",
                "estimators": estimators,
                "lags": lags,
                "fallback_values": values,
            },
        )

    def _statsforecast(self, history: pd.DataFrame) -> WorkerOutput:
        from statsforecast import StatsForecast

        models_module = importlib.import_module("statsforecast.models")
        cls = getattr(models_module, self.spec.class_name)
        model = cls(**self.params)
        frame = canonical_to_long(history, self._columns(history))
        sf = StatsForecast(models=[model], freq="7D", n_jobs=1)
        sf.fit(df=frame)
        prediction = sf.predict(h=1)
        value_col = [c for c in prediction.columns if c not in {"unique_id", "ds"}][0]
        values = prediction.sort_values("unique_id")[value_col].to_numpy(float)
        return WorkerOutput(
            values,
            {"library": "statsforecast", "column": value_col},
            model_artifact_payload={
                "library": "statsforecast",
                "statsforecast": sf,
                "frame": frame,
                "value_col": value_col,
            },
        )

    def _mlforecast(self, history: pd.DataFrame) -> WorkerOutput:
        from mlforecast import MLForecast

        frame = canonical_to_long(history, self._columns(history))
        frame["ds"] = frame.groupby("unique_id").cumcount().astype(int)
        lags = self.params.get("lags", [1, 2, 3, 5, 10, 20])
        fit_params = {k: v for k, v in self.params.items() if k != "lags"}
        if self.spec.class_name == "Ridge":
            from sklearn.linear_model import Ridge

            estimator = Ridge(**fit_params)
        else:
            from lightgbm import LGBMRegressor

            estimator = LGBMRegressor(random_state=self.seed, verbosity=-1, **fit_params)
        forecast = MLForecast(models={self.spec.model_id: estimator}, freq=1, lags=lags)
        forecast.fit(frame)
        prediction = forecast.predict(1)
        values = prediction.sort_values("unique_id")[self.spec.model_id].to_numpy(float)
        return WorkerOutput(
            values,
            {"library": "mlforecast", "lags": lags},
            model_artifact_payload={
                "library": "mlforecast",
                "mlforecast": forecast,
                "frame": frame,
                "value_col": self.spec.model_id,
                "lags": lags,
            },
        )

    def _neuralforecast(self, history: pd.DataFrame) -> WorkerOutput:
        import torch
        from neuralforecast import NeuralForecast
        from neuralforecast.losses.pytorch import MAE

        models_module = importlib.import_module("neuralforecast.models")
        cls = getattr(models_module, self.spec.class_name)
        params = dict(self.params)
        params.setdefault("h", 1)
        params.setdefault("input_size", min(64, max(8, len(history) // 2)))
        params.setdefault("max_steps", 200)
        params.setdefault("val_check_steps", 50)
        params.setdefault("early_stop_patience_steps", 3)
        params.setdefault("loss", MAE())
        params.setdefault("random_seed", self.seed)
        accelerator = (
            "gpu"
            if self.device == "cuda" or (self.device == "auto" and torch.cuda.is_available())
            else "cpu"
        )
        params.setdefault("accelerator", accelerator)
        params.setdefault("devices", 1)
        if self.spec.class_name in {
            "TSMixer",
            "TimeMixer",
            "iTransformer",
        }:
            params.setdefault("n_series", 7)
        if self.spec.class_name == "TimesNet" and self.precision != "32":
            params.setdefault("precision", "32-true")
        model = cls(**params)
        nf = NeuralForecast(models=[model], freq="7D")
        frame = canonical_to_long(history, self._columns(history))

        # NeuralForecast requires a validation window whenever early stopping
        # is enabled. Keep it bounded so short fold histories remain usable.
        val_size = max(1, min(10, len(history) // 5))

        if len(history) - val_size < 2:
            raise ValueError(
                f"insufficient history for NeuralForecast validation: "
                f"rows={len(history)}, val_size={val_size}"
            )

        nf.fit(df=frame, val_size=val_size)
        prediction = nf.predict().reset_index()
        value_col = [c for c in prediction.columns if c not in {"unique_id", "ds", "index"}][0]
        values = prediction.sort_values("unique_id")[value_col].to_numpy(float)
        return WorkerOutput(
            values,
            {
                "library": "neuralforecast",
                "accelerator": accelerator,
                "column": value_col,
                "val_size": val_size,
                "params": params,
            },
            model_artifact_payload={
                "library": "neuralforecast",
                "neuralforecast": nf,
                "frame": frame,
                "value_col": value_col,
                "params": params,
                "val_size": val_size,
            },
        )

    def _neuralforecast_auto(self, history: pd.DataFrame) -> WorkerOutput:
        import torch
        from neuralforecast import NeuralForecast

        controls = {
            "backend",
            "num_samples",
            "cpus",
            "gpus",
            "parallel_trials",
            "refit_with_val",
            "search_strategy",
            "early_stop_patience_steps",
        }
        model_config = {k: v for k, v in self.params.items() if k not in controls}
        gpus = int(
            self.params.get(
                "gpus", 1 if (self.device in {"auto", "cuda"} and torch.cuda.is_available()) else 0
            )
        )
        request = AutoModelRequest(
            model_name=self.spec.class_name,
            h=1,
            config=model_config or None,
            backend=self.params.get("backend"),
            cpus=int(self.params.get("cpus", 4)),
            gpus=gpus,
            parallel_trials=int(self.params.get("parallel_trials", 1)),
            num_samples=int(self.params.get("num_samples", 10)),
            refit_with_val=bool(self.params.get("refit_with_val", False)),
            precision=self.precision,
            early_stop_patience_steps=self.params.get("early_stop_patience_steps"),
            n_series=len(self._columns(history)),
            random_seed=self.seed,
            search_strategy=self.params.get("search_strategy", "auto"),
        )
        plan = resolve_auto_model_plan(request)
        runtime_params = dict(self.params)
        runtime_params["accelerator"] = "gpu" if gpus else "cpu"
        runtime_params["devices"] = 1
        model = construct_auto_model(plan)
        nf = NeuralForecast(models=[model], freq="7D")
        frame = canonical_to_long(history, self._columns(history))
        val_size = max(1, min(10, len(history) // 5))
        nf.fit(df=frame, val_size=val_size)
        prediction = nf.predict().reset_index()
        value_col = [c for c in prediction.columns if c not in {"unique_id", "ds", "index"}][0]
        values = prediction.sort_values("unique_id")[value_col].to_numpy(float)
        return WorkerOutput(
            values,
            {
                "library": "neuralforecast_auto",
                "backend": plan.backend,
                "search_algorithm": plan.search_algorithm,
                "adjustments": list(plan.adjustments),
                "column": value_col,
                "val_size": val_size,
                "params": runtime_params,
            },
            model_artifact_payload={
                "library": "neuralforecast",
                "neuralforecast": nf,
                "frame": frame,
                "value_col": value_col,
                "params": runtime_params,
                "val_size": val_size,
                "auto_plan": {
                    "backend": plan.backend,
                    "search_algorithm": plan.search_algorithm,
                    "adjustments": list(plan.adjustments),
                    "constructor_kwargs": {
                        key: str(value)
                        for key, value in plan.constructor_kwargs.items()
                        if key != "config"
                    },
                },
            },
        )

    def _autohint(self, history: pd.DataFrame) -> WorkerOutput:
        if len(self._columns(history)) != 7:
            raise ValueError("AutoHINT currently requires exactly 7 coherent position series")
        from neuralforecast import NeuralForecast
        from neuralforecast.losses.pytorch import DistributionLoss
        from neuralforecast.models import HINT, DLinear

        frame, hierarchy = autohint_hierarchy_frame(history)
        loss = DistributionLoss(distribution="Normal", level=[80], num_samples=20)
        base_model_config = {
            "h": 1,
            "input_size": min(16, max(8, len(history) // 3)),
            "loss": loss,
            "valid_loss": loss,
            "max_steps": int(self.params.get("max_steps", 1)),
            "batch_size": int(self.params.get("batch_size", 8)),
            "learning_rate": float(self.params.get("learning_rate", 0.001)),
            "random_seed": self.seed,
            # AUDIT (Phase 11, 2026-07-31): hardcoded, unlike _neuralforecast/_neuralforecast_auto
            # which branch on self.device. Not yet reconciled with --device cuda/auto requests --
            # left as-is pending a deliberate decision (see audit trail), not silently changed here.
            "accelerator": "cpu",
            "devices": 1,
            "enable_progress_bar": False,
            "logger": False,
        }
        base_model = DLinear(**base_model_config)
        reconciliation_method = str(self.params.get("reconciliation", "BottomUp"))
        model = HINT(
            h=1,
            model=base_model,
            S=hierarchy["summation_matrix"],
            reconciliation=reconciliation_method,
        )
        nf = NeuralForecast(models=[model], freq="7D")
        val_size = max(1, min(5, len(history) // 10))
        nf.fit(df=frame, val_size=val_size)
        np.random.seed(self.seed)
        prediction = nf.predict(random_seed=self.seed).reset_index()
        value_col = [c for c in prediction.columns if c not in {"unique_id", "ds", "index"}][0]
        bottom_order = hierarchy["internal_bottom_series_order"]
        values = (
            prediction.set_index("unique_id").loc[bottom_order, value_col].to_numpy(dtype=float)
        )
        total = float(prediction.set_index("unique_id").loc["00-total", value_col])
        coherence_error = abs(total - float(values.sum()))
        serializable_config = {
            key: value
            for key, value in base_model_config.items()
            if key not in {"loss", "valid_loss"}
        }
        metadata = {
            "library": "neuralforecast_auto",
            "backend": "ray_required",
            "backend_execution": "fixed_hint_single_config",
            "base_model_class": "DLinear",
            "base_model_config": serializable_config,
            "reconciliation_method": reconciliation_method,
            "loss": "DistributionLoss(Normal)",
            "valid_loss": "DistributionLoss(Normal)",
            "column": value_col,
            "val_size": val_size,
            "hierarchy": {
                key: value for key, value in hierarchy.items() if key != "summation_matrix"
            },
            "coherence_error": coherence_error,
        }
        return WorkerOutput(
            values,
            metadata,
            model_artifact_payload={
                "library": "autohint_fixed",
                "neuralforecast": nf,
                "frame": frame,
                "value_col": value_col,
                "params": serializable_config,
                "hierarchy": hierarchy,
                "metadata": metadata,
            },
        )

    def _invoke_autogluon_subprocess(self, request: dict[str, Any]) -> dict[str, Any]:
        if not AUTOGLUON_ENV.exists():
            raise WorkerSubprocessError(
                "DEPENDENCY_MISSING", f"missing AutoGluon-TimeSeries environment: {AUTOGLUON_ENV}"
            )
        if not (AUTOGLUON_ENV / "uv.lock").exists():
            raise WorkerSubprocessError(
                "DEPENDENCY_MISSING",
                f"missing AutoGluon-TimeSeries lockfile: {AUTOGLUON_ENV / 'uv.lock'}",
            )
        if not AUTOGLUON_RUNNER.exists():
            raise WorkerSubprocessError(
                "PROVIDER_NOT_IMPLEMENTED",
                f"missing AutoGluon-TimeSeries runner: {AUTOGLUON_RUNNER}",
            )
        with tempfile.TemporaryDirectory(prefix="loto-autogluon-ts-") as tmp:
            request_path = Path(tmp) / "provider_request.json"
            response_path = Path(tmp) / "provider_response.json"
            request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(AUTOGLUON_ENV),
                    "python",
                    str(AUTOGLUON_RUNNER),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=int(self.params.get("provider_timeout", 900)),
                check=False,
            )
            if proc.returncode != 0:
                raise WorkerSubprocessError(
                    "ERROR",
                    f"AutoGluon-TimeSeries subprocess failed rc={proc.returncode}: {proc.stderr[-2000:] or proc.stdout[-2000:]}",
                )
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise WorkerSubprocessError(
                    "ERROR", f"AutoGluon-TimeSeries provider returned invalid JSON: {exc}"
                ) from exc
        if response.get("status") != "OK":
            raise WorkerSubprocessError(
                str(response.get("status", "ERROR")),
                str(response.get("message", "AutoGluon-TimeSeries provider failed")),
            )
        predictions = np.asarray(response.get("predictions"), dtype=float)
        expected = len(request.get("position_columns", [])) or len(self._columns(history))
        if predictions.shape != (expected,) or not np.isfinite(predictions).all():
            raise WorkerSubprocessError(
                "PREDICTION_MISMATCH",
                f"AutoGluon-TimeSeries provider returned invalid predictions shape={predictions.shape}",
            )
        return response

    def _autogluon(self, history: pd.DataFrame) -> WorkerOutput:
        columns = [*self._columns(history), "draw_date"]
        payload = history[columns].copy()
        payload["draw_date"] = payload["draw_date"].astype(str)
        artifact_dir = tempfile.mkdtemp(prefix="loto-autogluon-artifact-")
        request = {
            "schema_version": 1,
            "model_id": self.spec.model_id,
            "mode": "fit_predict_save",
            "artifact_dir": artifact_dir,
            "history": payload.to_dict(orient="records"),
            "position_columns": self._columns(history),
            "presets": self.params.get("presets", "fast_training"),
            "time_limit": self.params.get("time_limit", 120),
            "prediction_length": 1,
            "eval_metric": "MAE",
            "seed": self.seed,
            "device": self.device if self.device != "auto" else "cpu",
        }
        response = self._invoke_autogluon_subprocess(request)
        values = np.asarray(response["predictions"], dtype=float)
        properties = response.get("properties", {})
        return WorkerOutput(
            values,
            {
                "library": "autogluon",
                "model_best": properties.get("model_best"),
                "presets": properties.get("presets"),
            },
            model_artifact_payload={
                "library": "autogluon",
                "artifact_dir": artifact_dir,
                "request": request,
                "response": response,
            },
        )

    def _darts(self, history: pd.DataFrame) -> WorkerOutput:
        from darts import TimeSeries
        from darts.models import ExponentialSmoothing, NaiveDrift, RegressionEnsembleModel

        models = []
        values = []
        for position, column in enumerate(self._columns(history), start=1):
            source_series = history.set_index("draw_no")[column].astype(float)
            series = TimeSeries.from_series(source_series)
            model = RegressionEnsembleModel(
                forecasting_models=[NaiveDrift(), ExponentialSmoothing()],
                regression_train_n_points=min(20, max(5, len(source_series) // 4)),
            )
            model.fit(series)
            values.append(float(model.predict(1).values()[0, 0]))
            models.append(model)
        metadata = {
            "library": "darts",
            "component_models": ["NaiveDrift", "ExponentialSmoothing"],
            "ensemble_model": "RegressionEnsembleModel",
            "ensemble_method": "regression",
            "regression_train_n_points": min(20, max(5, len(history) // 4)),
        }
        return WorkerOutput(
            np.asarray(values),
            metadata,
            model_artifact_payload={
                "library": "darts_ensemble",
                "models": models,
                "metadata": metadata,
            },
        )

    def _gluonts(self, history: pd.DataFrame) -> WorkerOutput:
        import torch
        from gluonts.dataset.common import ListDataset
        from gluonts.torch.distributions import StudentTOutput
        from gluonts.torch.model.deepar import DeepAREstimator

        torch.manual_seed(self.seed)
        original_torch_load = torch.load

        def _torch_load_allow_local_checkpoint(*args, **kwargs):
            if kwargs.get("weights_only") is not False:
                kwargs["weights_only"] = False
            return original_torch_load(*args, **kwargs)

        torch.load = _torch_load_allow_local_checkpoint
        frame = []
        for position, column in enumerate(self._columns(history), start=1):
            frame.append(
                {
                    "start": pd.Timestamp(history["draw_date"].iloc[0]),
                    "target": history[column].astype(float).to_numpy(),
                }
            )
        dataset = ListDataset(frame, freq="D")
        estimator = DeepAREstimator(
            freq="D",
            prediction_length=1,
            context_length=int(self.params.get("context_length", 16)),
            num_layers=1,
            hidden_size=8,
            batch_size=4,
            num_batches_per_epoch=int(self.params.get("num_batches_per_epoch", 2)),
            num_parallel_samples=int(self.params.get("num_samples", 20)),
            distr_output=StudentTOutput(),
            trainer_kwargs={
                "max_epochs": int(self.params.get("epochs", 1)),
                # AUDIT (Phase 11, 2026-07-31): hardcoded, unlike _neuralforecast/_neuralforecast_auto
                # which branch on self.device. Not yet reconciled with --device cuda/auto requests --
                # left as-is pending a deliberate decision (see audit trail), not silently changed here.
                "accelerator": "cpu",
                "devices": 1,
                "logger": False,
                "enable_progress_bar": False,
            },
        )
        try:
            predictor = estimator.train(dataset)
        finally:
            torch.load = original_torch_load
        forecasts = list(predictor.predict(dataset))
        values = np.asarray(
            [float(np.asarray(forecast.samples).mean(axis=0)[0]) for forecast in forecasts]
        )
        metadata = {
            "library": "gluonts",
            "backend": "torch",
            "estimator_class": "DeepAREstimator",
            "trainer_configuration": {
                "max_epochs": int(self.params.get("epochs", 1)),
                "num_batches_per_epoch": int(self.params.get("num_batches_per_epoch", 2)),
                "context_length": int(self.params.get("context_length", 16)),
                "prediction_length": 1,
                "num_parallel_samples": int(self.params.get("num_samples", 20)),
            },
            "distribution_output": "StudentTOutput",
            "prediction_samples": int(self.params.get("num_samples", 20)),
        }
        return WorkerOutput(
            values,
            metadata,
            model_artifact_payload={
                "library": "gluonts_deepar",
                "predictor": predictor,
                "dataset": list(frame),
                "metadata": metadata,
            },
        )

    def _reservoir_esn(self, history: pd.DataFrame) -> WorkerOutput:
        import reservoirpy as rpy
        from reservoirpy.nodes import Reservoir, Ridge

        units = int(self.params.get("units", self.params.get("reservoir_size", 50)))
        spectral_radius = float(self.params.get("spectral_radius", 0.9))
        leak_rate = float(self.params.get("leak_rate", 0.3))
        ridge_alpha = float(self.params.get("ridge", self.params.get("ridge_alpha", 1e-6)))
        models = []
        values = []
        for position, column in enumerate(self._columns(history), start=1):
            series = history[column].astype(float).to_numpy()
            x_train = series[:-1].reshape(-1, 1)
            y_train = series[1:].reshape(-1, 1)
            reservoir = Reservoir(
                units=units,
                sr=spectral_radius,
                lr=leak_rate,
                input_dim=1,
                seed=self.seed + position,
            )
            readout = Ridge(ridge=ridge_alpha, output_dim=1)
            model = reservoir >> readout
            model.fit(x_train, y_train)
            prediction = model.run(series[-1:].reshape(1, 1))
            values.append(float(np.asarray(prediction).reshape(-1)[-1]))
            models.append(model)
        metadata = {
            "library": "reservoirpy",
            "package_version": getattr(rpy, "__version__", "unknown"),
            "implementation": "reservoirpy.nodes.Reservoir>>Ridge",
            "reservoir_size": units,
            "spectral_radius": spectral_radius,
            "leak_rate": leak_rate,
            "ridge_alpha": ridge_alpha,
            "random_seed": self.seed,
        }
        return WorkerOutput(
            np.asarray(values, dtype=float),
            metadata,
            model_artifact_payload={
                "library": "reservoirpy_esn",
                "models": models,
                "metadata": metadata,
            },
        )

    def _foundation(self, history: pd.DataFrame) -> WorkerOutput:
        provider_cls = get_foundation_provider(self.spec)
        provider = provider_cls(
            self.spec, self.params, seed=self.seed, device=self.device, precision=self.precision
        )
        try:
            provider.load()
            values = provider.predict(history)
            return WorkerOutput(values, provider.inspect_properties())
        except FoundationProviderError:
            raise
        finally:
            provider.close()
