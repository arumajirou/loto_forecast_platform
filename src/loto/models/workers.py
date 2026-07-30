from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.models.catalog import ModelSpec
from loto.models.neuralforecast_adapter import AutoModelRequest, construct_auto_model, resolve_auto_model_plan


@dataclass
class WorkerOutput:
    position_values: np.ndarray
    metadata: dict[str, Any]
    candidate_probabilities: np.ndarray | None = None


def canonical_to_long(master: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in master.itertuples(index=False):
        for position in range(1, 8):
            records.append({
                "unique_id": f"position-{position}",
                "ds": pd.Timestamp(row.draw_date),
                "y": float(getattr(row, f"n{position}")),
            })
    return pd.DataFrame(records).sort_values(["unique_id", "ds"]).reset_index(drop=True)


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


def position_values_to_candidate_probabilities(history: pd.DataFrame, values: np.ndarray) -> np.ndarray:
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
        run_id: str | None = None,
        trial_id: str | None = None,
        fold_id: str | None = None,
        output_dir: str | Path | None = None,
    ):
        self.spec = spec
        self.params = spec.default_params | (params or {})
        self.seed = seed
        self.device = device
        self.precision = precision
        self.run_id = run_id
        self.trial_id = trial_id
        self.fold_id = fold_id
        self.output_dir = (
            Path(output_dir)
            if output_dir is not None
            else None
        )

    def forecast(self, history: pd.DataFrame) -> WorkerOutput:
        if self.spec.library in {"sklearn", "lightgbm"}:
            output = self._lag_regression(history)
        elif self.spec.library == "statsforecast":
            output = self._statsforecast(history)
        elif self.spec.library == "mlforecast":
            output = self._mlforecast(history)
        elif self.spec.library == "neuralforecast":
            output = self._neuralforecast(history)
        elif self.spec.library == "neuralforecast_auto":
            output = self._neuralforecast_auto(history)
        elif self.spec.library == "autogluon":
            output = self._autogluon(history)
        elif self.spec.library == "darts":
            output = self._darts(history)
        elif self.spec.library == "gluonts":
            output = self._gluonts(history)
        elif self.spec.library in {"chronos", "timesfm", "transformers", "tirex", "uni2ts"}:
            output = self._foundation(history)
        else:
            raise NotImplementedError(f"no position worker for library={self.spec.library}")
        if output.candidate_probabilities is None:
            output.candidate_probabilities = position_values_to_candidate_probabilities(history, output.position_values)
        return output

    def _lag_regression(self, history: pd.DataFrame) -> WorkerOutput:
        lags = list(self.params.get("lags", [1, 2, 3, 5, 10, 20]))
        lags = sorted({int(lag) for lag in lags if int(lag) > 0})
        fit_params = {k: v for k, v in self.params.items() if k != "lags"}
        values: list[float] = []
        for position in range(1, 8):
            series = history[f"n{position}"].astype(float).to_numpy()
            max_lag = max(lags)
            if len(series) <= max_lag + 2:
                values.append(float(np.median(series)))
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
            values.append(float(estimator.predict(query)[0]))
        return WorkerOutput(np.asarray(values), {"library": self.spec.library, "lags": lags})

    def _statsforecast(self, history: pd.DataFrame) -> WorkerOutput:
        from statsforecast import StatsForecast

        models_module = importlib.import_module("statsforecast.models")
        cls = getattr(models_module, self.spec.class_name)
        model = cls(**self.params)
        frame = canonical_to_long(history)
        sf = StatsForecast(models=[model], freq="7D", n_jobs=1)
        prediction = sf.forecast(df=frame, h=1)
        value_col = [c for c in prediction.columns if c not in {"unique_id", "ds"}][0]
        values = prediction.sort_values("unique_id")[value_col].to_numpy(float)
        return WorkerOutput(values, {"library": "statsforecast", "column": value_col})

    def _mlforecast(self, history: pd.DataFrame) -> WorkerOutput:
        from mlforecast import MLForecast

        frame = canonical_to_long(history)
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
        return WorkerOutput(values, {"library": "mlforecast", "lags": lags})

    def _neuralforecast_artifact_dirs(self) -> dict[str, Path] | None:
        if self.output_dir is None:
            return None

        model_root = (
            self.output_dir
            / "models"
            / self.spec.model_id
            / f"seed-{self.seed}"
            / str(self.fold_id or "fold-unknown")
        )

        tensorboard_root = (
            self.output_dir
            / "tensorboard"
            / self.spec.model_id
            / f"seed-{self.seed}"
        )

        checkpoint_root = model_root / "checkpoints"
        saved_model_root = model_root / "neuralforecast"

        for directory in (
            model_root,
            tensorboard_root,
            checkpoint_root,
            saved_model_root,
        ):
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

        return {
            "model_root": model_root,
            "tensorboard_root": tensorboard_root,
            "checkpoint_root": checkpoint_root,
            "saved_model_root": saved_model_root,
        }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as stream:
            for block in iter(
                lambda: stream.read(1024 * 1024),
                b"",
            ):
                digest.update(block)

        return digest.hexdigest()

    def _write_neuralforecast_properties(
        self,
        *,
        params: dict[str, Any],
        metadata: dict[str, Any],
        directories: dict[str, Path],
    ) -> dict[str, Any]:
        checkpoint_files = sorted(
            directories["model_root"].rglob("*.ckpt")
        )

        checkpoints = []

        for checkpoint in checkpoint_files:
            checkpoints.append({
                "path": str(checkpoint),
                "bytes": checkpoint.stat().st_size,
                "sha256": self._sha256(checkpoint),
            })

        properties = {
            "schema_version": "1.0.0",
            "run_id": self.run_id,
            "trial_id": self.trial_id,
            "fold_id": self.fold_id,
            "model_id": self.spec.model_id,
            "class_name": self.spec.class_name,
            "library": self.spec.library,
            "seed": self.seed,
            "device": self.device,
            "precision": self.precision,
            "resolved_params": {
                key: str(value)
                for key, value in params.items()
            },
            "metadata": metadata,
            "checkpoints": checkpoints,
        }

        properties_path = (
            directories["model_root"]
            / "model-properties.json"
        )

        properties_path.write_text(
            json.dumps(
                properties,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        sha_path = (
            directories["model_root"]
            / "checkpoint-sha256.txt"
        )

        sha_path.write_text(
            "".join(
                f"{item['sha256']}  {item['path']}\n"
                for item in checkpoints
            ),
            encoding="utf-8",
        )

        return {
            "model_root": str(
                directories["model_root"]
            ),
            "tensorboard_root": str(
                directories["tensorboard_root"]
            ),
            "checkpoint_root": str(
                directories["checkpoint_root"]
            ),
            "saved_model_root": str(
                directories["saved_model_root"]
            ),
            "model_properties": str(properties_path),
            "checkpoint_manifest": str(sha_path),
            "checkpoint_count": len(checkpoints),
        }

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
        accelerator = "gpu" if self.device == "cuda" or (self.device == "auto" and torch.cuda.is_available()) else "cpu"
        params.setdefault("accelerator", accelerator)
        params.setdefault("devices", 1)

        directories = self._neuralforecast_artifact_dirs()

        if directories is not None:
            from pytorch_lightning.callbacks import (
                ModelCheckpoint,
            )
            from pytorch_lightning.loggers import (
                TensorBoardLogger,
            )

            logger = TensorBoardLogger(
                save_dir=str(
                    directories["tensorboard_root"]
                ),
                name="",
                version=str(
                    self.fold_id or "fold-unknown"
                ),
                default_hp_metric=True,
            )

            checkpoint_callback = ModelCheckpoint(
                dirpath=str(
                    directories["checkpoint_root"]
                ),
                filename=(
                    "{epoch:03d}-{step:06d}"
                    "-{ptl_val_loss:.6f}"
                ),
                monitor="ptl/val_loss",
                mode="min",
                save_top_k=1,
                save_last=True,
                auto_insert_metric_name=False,
            )

            params.setdefault("logger", logger)
            params.setdefault(
                "callbacks",
                [checkpoint_callback],
            )
            params.setdefault(
                "enable_checkpointing",
                True,
            )
            params.setdefault(
                "default_root_dir",
                str(directories["model_root"]),
            )

        if self.spec.class_name == "TSMixer":
            params.setdefault("n_series", 7)
        if self.spec.class_name == "TimesNet" and self.precision != "32":
            params.setdefault("precision", "32-true")
        model = cls(**params)
        nf = NeuralForecast(models=[model], freq="7D")
        frame = canonical_to_long(history)

        early_stop_patience = int(
            params.get("early_stop_patience_steps", -1)
        )
        if early_stop_patience >= 0:
            val_size = max(1, min(10, len(history) // 5))
        else:
            val_size = 0

        nf.fit(df=frame, val_size=val_size)

        artifact_metadata: dict[str, Any] = {}

        if directories is not None:
            nf.save(
                path=str(
                    directories["saved_model_root"]
                ),
                overwrite=True,
            )

        prediction = nf.predict().reset_index()
        value_col = [c for c in prediction.columns if c not in {"unique_id", "ds", "index"}][0]
        values = prediction.sort_values(
            "unique_id"
        )[value_col].to_numpy(float)

        metadata = {
            "library": "neuralforecast",
            "accelerator": accelerator,
            "column": value_col,
            "val_size": val_size,
            "early_stop_patience_steps": (
                early_stop_patience
            ),
            "run_id": self.run_id,
            "trial_id": self.trial_id,
            "fold_id": self.fold_id,
        }

        if directories is not None:
            artifact_metadata = (
                self._write_neuralforecast_properties(
                    params=params,
                    metadata=metadata,
                    directories=directories,
                )
            )
            metadata["artifacts"] = artifact_metadata

        return WorkerOutput(
            values,
            metadata,
        )

    def _neuralforecast_auto(self, history: pd.DataFrame) -> WorkerOutput:
        import torch
        from neuralforecast import NeuralForecast

        controls = {
            "backend", "num_samples", "cpus", "gpus", "parallel_trials", "refit_with_val",
            "search_strategy", "early_stop_patience_steps",
        }
        model_config = {k: v for k, v in self.params.items() if k not in controls}
        gpus = int(self.params.get("gpus", 1 if (self.device in {"auto", "cuda"} and torch.cuda.is_available()) else 0))
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
            n_series=7,
            random_seed=self.seed,
            search_strategy=self.params.get("search_strategy", "auto"),
        )
        plan = resolve_auto_model_plan(request)
        model = construct_auto_model(plan)
        nf = NeuralForecast(models=[model], freq="7D")
        frame = canonical_to_long(history)
        val_size = max(1, min(10, len(history) // 5))
        nf.fit(df=frame, val_size=val_size)
        prediction = nf.predict().reset_index()
        value_col = [c for c in prediction.columns if c not in {"unique_id", "ds", "index"}][0]
        values = prediction.sort_values("unique_id")[value_col].to_numpy(float)
        return WorkerOutput(values, {
            "library": "neuralforecast_auto",
            "backend": plan.backend,
            "search_algorithm": plan.search_algorithm,
            "adjustments": list(plan.adjustments),
            "column": value_col,
            "val_size": val_size,
        })

    def _autogluon(self, history: pd.DataFrame) -> WorkerOutput:
        from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

        frame = canonical_to_long(history).rename(columns={"unique_id": "item_id", "ds": "timestamp", "y": "target"})
        ts = TimeSeriesDataFrame.from_data_frame(frame, id_column="item_id", timestamp_column="timestamp")
        predictor = TimeSeriesPredictor(prediction_length=1, target="target", eval_metric="MAE")
        predictor.fit(ts, presets=self.params.get("presets", "medium_quality"), time_limit=self.params.get("time_limit"))
        pred = predictor.predict(ts)
        values = pred.reset_index().sort_values("item_id")["mean"].to_numpy(float)
        return WorkerOutput(values, {"library": "autogluon", "model_best": predictor.model_best})

    def _darts(self, history: pd.DataFrame) -> WorkerOutput:
        from darts import TimeSeries
        from darts.models import ExponentialSmoothing, NaiveDrift, RegressionEnsembleModel

        values = []
        for position in range(1, 8):
            series = TimeSeries.from_series(history.set_index("draw_date")[f"n{position}"].astype(float))
            model = RegressionEnsembleModel(
                forecasting_models=[NaiveDrift(), ExponentialSmoothing()],
                regression_train_n_points=min(20, max(5, len(series) // 4)),
            )
            model.fit(series)
            values.append(float(model.predict(1).values()[0, 0]))
        return WorkerOutput(np.asarray(values), {"library": "darts"})

    def _gluonts(self, history: pd.DataFrame) -> WorkerOutput:
        raise RuntimeError("GluonTS worker requires an estimator-specific plugin; use model plugin entry point")

    def _foundation(self, history: pd.DataFrame) -> WorkerOutput:
        model_name = self.params.get("model_name")
        if self.spec.library == "chronos":
            import torch
            from chronos import ChronosPipeline

            pipeline = ChronosPipeline.from_pretrained(model_name, device_map=self.device, torch_dtype=torch.float32)
            context = torch.tensor(history[[f"n{i}" for i in range(1, 8)]].to_numpy(float).T)
            samples = pipeline.predict(context, prediction_length=1)
            values = np.median(samples.detach().cpu().numpy(), axis=1).reshape(7)
            return WorkerOutput(values, {"library": "chronos", "model_name": model_name})
        raise RuntimeError(
            f"foundation worker {self.spec.model_id} requires its provider plugin; "
            "the job contract and registry entry are available"
        )
