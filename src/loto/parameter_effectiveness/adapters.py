"""Built-in forecasting-library adapters.

Imports are lazy so the core harness stays usable when an optional forecasting
library is not installed.  The adapters use deterministic synthetic
Development data only; they never read project Holdout or Prospective actuals.
"""

from __future__ import annotations

import hashlib
import inspect
import time
from typing import Any

import numpy as np
import pandas as pd

from .contracts import EffectSurface, ParameterProbeSpec, ParameterScope, ProbeRunObservation
from .core import AdapterRegistry


def _prediction_sha(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.float64)
    payload = str(array.shape).encode("ascii") + array.tobytes()
    return hashlib.sha256(payload).hexdigest()


def _hit_at_1(prediction: np.ndarray, actual: np.ndarray) -> float:
    return float(np.mean(np.abs(prediction - actual) <= 1.0))


def _mlforecast_panel(seed: int, repeat: int, train_length: int = 96) -> pd.DataFrame:
    rng = np.random.default_rng(seed + repeat * 100_003)
    frames: list[pd.DataFrame] = []

    for position, offset in (("d1", 0.0), ("d2", 2.0), ("d3", 4.0)):
        t = np.arange(train_length, dtype=float)
        deterministic = (offset + 0.12 * t + 1.8 * np.sin(t / 5.0)) % 10.0
        noise = rng.normal(0.0, 0.03, size=train_length)
        frames.append(
            pd.DataFrame(
                {
                    "unique_id": position,
                    "ds": np.arange(1, train_length + 1, dtype=int),
                    "y": deterministic + noise,
                }
            )
        )

    return pd.concat(frames, ignore_index=True)


def _mlforecast_future_actual(seed: int, repeat: int, h: int, train_length: int = 96) -> np.ndarray:
    rng = np.random.default_rng(seed + repeat * 100_003)
    # Advance the deterministic RNG by the exact training draws used above.
    for _ in range(3):
        rng.normal(0.0, 0.03, size=train_length)

    values: list[float] = []
    for offset in (0.0, 2.0, 4.0):
        t = np.arange(train_length, train_length + h, dtype=float)
        deterministic = (offset + 0.12 * t + 1.8 * np.sin(t / 5.0)) % 10.0
        values.extend(deterministic.tolist())
    return np.asarray(values, dtype=float)


class MLForecastParameterAdapter:
    """Probe AutoMLForecast arguments and Auto-model constructor arguments."""

    library = "mlforecast"

    _library_constructor = {"num_threads", "reuse_cv_splits", "season_length"}
    _fit = {"num_samples", "input_size", "refit", "n_windows", "step_size"}

    def _imports(self) -> tuple[type[Any], dict[str, type[Any]]]:
        from mlforecast.auto import (  # type: ignore[import-untyped]
            AutoCatboost,
            AutoElasticNet,
            AutoLasso,
            AutoLightGBM,
            AutoLinearRegression,
            AutoMLForecast,
            AutoRandomForest,
            AutoRidge,
            AutoXGBoost,
        )

        classes = {
            "AutoLightGBM": AutoLightGBM,
            "AutoXGBoost": AutoXGBoost,
            "AutoCatboost": AutoCatboost,
            "AutoRandomForest": AutoRandomForest,
            "AutoElasticNet": AutoElasticNet,
            "AutoLasso": AutoLasso,
            "AutoRidge": AutoRidge,
            "AutoLinearRegression": AutoLinearRegression,
        }
        return AutoMLForecast, classes

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        try:
            _, classes = self._imports()
        except ImportError as exc:
            return False, f"MLForecast unavailable: {exc}"

        if spec.model not in classes:
            return False, f"unsupported MLForecast Auto model: {spec.model}"

        if spec.scope is ParameterScope.AUTO:
            known = spec.parameter in self._library_constructor | self._fit
            if not known:
                return False, (
                    "AUTO scope only routes known AutoMLForecast arguments; "
                    "use model_constructor for Auto-model constructor arguments"
                )

        if spec.expected_surface is EffectSurface.TRIAL_COUNT and spec.parameter != "num_samples":
            return False, "trial_count surface is only exposed for num_samples"

        if spec.expected_surface is EffectSurface.HISTORY and spec.parameter != "input_size":
            return False, "history surface is only exposed for input_size"

        return True, None

    @staticmethod
    def _scope(spec: ParameterProbeSpec) -> ParameterScope:
        if spec.scope is not ParameterScope.AUTO:
            return spec.scope
        if spec.parameter in MLForecastParameterAdapter._library_constructor:
            return ParameterScope.LIBRARY_CONSTRUCTOR
        return ParameterScope.FIT

    def run(
        self,
        spec: ParameterProbeSpec,
        value: Any,
        seed: int,
        repeat: int,
    ) -> ProbeRunObservation:
        started = time.perf_counter()

        try:
            auto_mlforecast, classes = self._imports()
            model_class = classes[spec.model]
            scope = self._scope(spec)

            base = dict(spec.base_args)
            model_kwargs = dict(base.pop("model_kwargs", {}))
            constructor_kwargs = {
                "freq": base.pop("freq", 1),
                "season_length": base.pop("season_length", 1),
                "num_threads": base.pop("num_threads", 1),
                "reuse_cv_splits": base.pop("reuse_cv_splits", True),
            }
            fit_kwargs = {
                "n_windows": base.pop("n_windows", 2),
                "h": base.pop("h", 1),
                "num_samples": base.pop("num_samples", 2),
                "step_size": base.pop("step_size", 1),
                "input_size": base.pop("input_size", None),
                "refit": base.pop("refit", False),
            }
            if base:
                unknown = ", ".join(sorted(base))
                raise ValueError(f"unknown MLForecast base_args: {unknown}")

            if scope is ParameterScope.MODEL_CONSTRUCTOR:
                model_kwargs[spec.parameter] = value
            elif scope is ParameterScope.LIBRARY_CONSTRUCTOR:
                constructor_kwargs[spec.parameter] = value
            elif scope is ParameterScope.FIT:
                fit_kwargs[spec.parameter] = value
            else:
                raise ValueError(f"unsupported MLForecast parameter scope: {scope.value}")

            model = model_class(**model_kwargs)
            automl = auto_mlforecast(
                models={spec.model: model},
                **constructor_kwargs,
            )

            frame = _mlforecast_panel(seed, repeat)

            automl.fit(
                df=frame,
                id_col="unique_id",
                time_col="ds",
                target_col="y",
                study_kwargs={
                    "sampler": self._sampler(seed),
                },
                optimize_kwargs={"n_jobs": 1},
                **fit_kwargs,
            )

            h = int(fit_kwargs["h"])
            prediction_frame = automl.predict(h=h)
            if spec.model not in prediction_frame.columns:
                raise RuntimeError(f"prediction column missing: {spec.model}")

            prediction = prediction_frame[spec.model].to_numpy(dtype=float)
            finite = bool(np.isfinite(prediction).all())
            if not finite:
                raise RuntimeError("prediction contains NaN/Inf")

            study = automl.results_[spec.model]
            actual = _mlforecast_future_actual(seed, repeat, h)
            if actual.shape != prediction.shape:
                # AutoMLForecast orders panel forecasts by id then horizon.
                actual = actual[: prediction.size]

            input_size = fit_kwargs.get("input_size")
            effective_history = 96 if input_size is None else min(96, int(input_size))

            observables: dict[str, int | float | bool | str | None] = {
                "trial_count": len(study.trials),
                "history": effective_history,
                "metric": _hit_at_1(prediction, actual),
                "best_value": float(study.best_value),
            }

            return ProbeRunObservation(
                accepted=True,
                success=True,
                finite=True,
                output_shape=tuple(int(item) for item in prediction_frame.shape),
                prediction_sha256=_prediction_sha(prediction),
                observables=observables,
                runtime_seconds=time.perf_counter() - started,
                metadata={
                    "adapter": type(self).__name__,
                    "model_signature": str(inspect.signature(model_class)),
                    "fit_signature": str(inspect.signature(auto_mlforecast.fit)),
                },
            )
        except Exception as exc:
            return ProbeRunObservation(
                accepted=False,
                success=False,
                finite=False,
                runtime_seconds=time.perf_counter() - started,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _sampler(seed: int) -> Any:
        import optuna  # type: ignore[import-untyped]

        return optuna.samplers.TPESampler(seed=seed)


class StatsForecastParameterAdapter:
    """Probe StatsForecast model-constructor arguments with real forecasts."""

    library = "statsforecast"

    def _imports(self) -> tuple[type[Any], Any]:
        from statsforecast import (  # type: ignore[import-untyped]
            StatsForecast,
            models,
        )

        return StatsForecast, models

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        try:
            _, models = self._imports()
        except ImportError as exc:
            return False, f"StatsForecast unavailable: {exc}"

        model_class = getattr(models, spec.model, None)
        if model_class is None:
            return False, f"unknown StatsForecast model: {spec.model}"

        if spec.scope not in {ParameterScope.AUTO, ParameterScope.MODEL_CONSTRUCTOR}:
            return False, "StatsForecast adapter currently probes model-constructor arguments"

        signature = inspect.signature(model_class)
        if spec.parameter not in signature.parameters:
            return False, f"{spec.parameter!r} is not in {spec.model} constructor"

        if spec.expected_surface in {EffectSurface.TRIAL_COUNT, EffectSurface.HISTORY}:
            return False, f"{spec.expected_surface.value} is not exposed by StatsForecast adapter"

        return True, None

    @staticmethod
    def _signal(seed: int, repeat: int, length: int) -> np.ndarray:
        rng = np.random.default_rng(seed + repeat * 100_003)
        t = np.arange(length, dtype=float)
        return (
            4.0
            + 1.7 * np.sin(2.0 * np.pi * t / 7.0)
            + 0.6 * np.cos(2.0 * np.pi * t / 3.0)
            + 0.015 * t
            + rng.normal(0.0, 0.01, size=length)
        )

    def run(
        self,
        spec: ParameterProbeSpec,
        value: Any,
        seed: int,
        repeat: int,
    ) -> ProbeRunObservation:
        started = time.perf_counter()

        try:
            statsforecast_class, models = self._imports()
            model_class = getattr(models, spec.model)

            base = dict(spec.base_args)
            h = int(base.pop("h", 7))
            train_length = int(base.pop("train_length", 84))
            freq = str(base.pop("freq", "D"))
            n_jobs = int(base.pop("n_jobs", 1))
            model_kwargs = dict(base.pop("model_kwargs", {}))
            if base:
                unknown = ", ".join(sorted(base))
                raise ValueError(f"unknown StatsForecast base_args: {unknown}")

            model_kwargs[spec.parameter] = value
            model = model_class(**model_kwargs)

            complete = self._signal(seed, repeat, train_length + h)
            train = complete[:train_length]
            actual = complete[train_length:]

            frame = pd.DataFrame(
                {
                    "unique_id": "series-1",
                    "ds": pd.date_range("2000-01-01", periods=train_length, freq=freq),
                    "y": train,
                }
            )

            engine = statsforecast_class(models=[model], freq=freq, n_jobs=n_jobs)
            forecast = engine.forecast(df=frame, h=h)

            candidate_columns = [
                column
                for column in forecast.columns
                if column not in {"unique_id", "ds"}
            ]
            if len(candidate_columns) != 1:
                raise RuntimeError(f"expected one forecast column, got {candidate_columns}")

            prediction = forecast[candidate_columns[0]].to_numpy(dtype=float)
            finite = bool(np.isfinite(prediction).all())
            if not finite:
                raise RuntimeError("prediction contains NaN/Inf")
            if prediction.shape != actual.shape:
                raise RuntimeError(
                    f"prediction shape {prediction.shape} does not match actual {actual.shape}"
                )

            return ProbeRunObservation(
                accepted=True,
                success=True,
                finite=True,
                output_shape=tuple(int(item) for item in forecast.shape),
                prediction_sha256=_prediction_sha(prediction),
                observables={
                    "metric": _hit_at_1(prediction, actual),
                },
                runtime_seconds=time.perf_counter() - started,
                metadata={
                    "adapter": type(self).__name__,
                    "forecast_column": candidate_columns[0],
                    "model_signature": str(inspect.signature(model_class)),
                },
            )
        except Exception as exc:
            return ProbeRunObservation(
                accepted=False,
                success=False,
                finite=False,
                runtime_seconds=time.perf_counter() - started,
                error=f"{type(exc).__name__}: {exc}",
            )


def default_registry() -> AdapterRegistry:
    """Return the built-in registry without importing optional libraries."""

    registry = AdapterRegistry()
    registry.register(MLForecastParameterAdapter(), "automlforecast")
    registry.register(StatsForecastParameterAdapter())
    return registry
