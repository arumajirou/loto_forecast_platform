"""Phase 5B adapters for additional certified forecasting runtime families.

All optional forecasting-library imports are lazy. The adapters use deterministic
Development-only synthetic signals and never read Holdout or Prospective actuals.
"""

from __future__ import annotations

import hashlib
import inspect
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import EffectSurface, ParameterProbeSpec, ParameterScope, ProbeRunObservation


def _prediction_sha(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.float64)
    payload = str(array.shape).encode("ascii") + array.tobytes()
    return hashlib.sha256(payload).hexdigest()


def _signal(seed: int, repeat: int, length: int = 96) -> np.ndarray:
    rng = np.random.default_rng(seed + repeat * 100_003)
    t = np.arange(length, dtype=float)
    return (
        7.0
        + 1.6 * np.sin(2.0 * np.pi * t / 7.0)
        + 0.9 * np.cos(2.0 * np.pi * t / 5.0)
        + 0.025 * t
        + rng.normal(0.0, 0.01, size=length)
    )


class DartsParameterAdapter:
    """Probe Darts NaiveSeasonal constructor arguments with real predictions."""

    library = "darts"

    def _imports(self) -> tuple[type[Any], type[Any]]:
        from darts import TimeSeries  # type: ignore[import-untyped]
        from darts.models import NaiveSeasonal  # type: ignore[import-untyped]

        return TimeSeries, NaiveSeasonal

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        try:
            _, model_class = self._imports()
        except ImportError as exc:
            return False, f"Darts unavailable: {exc}"
        if spec.model != "NaiveSeasonal":
            return False, f"unsupported Darts model: {spec.model}"
        if spec.scope not in {ParameterScope.AUTO, ParameterScope.MODEL_CONSTRUCTOR}:
            return False, "Darts adapter probes NaiveSeasonal model-constructor arguments"
        if spec.parameter not in inspect.signature(model_class).parameters:
            return False, f"{spec.parameter!r} is not in NaiveSeasonal constructor"
        if spec.expected_surface in {EffectSurface.TRIAL_COUNT, EffectSurface.HISTORY}:
            return False, f"{spec.expected_surface.value} is not exposed by Darts adapter"
        return True, None

    def run(
        self,
        spec: ParameterProbeSpec,
        value: Any,
        seed: int,
        repeat: int,
    ) -> ProbeRunObservation:
        started = time.perf_counter()
        try:
            time_series, model_class = self._imports()
            base = dict(spec.base_args)
            h = int(base.pop("h", 7))
            train_length = int(base.pop("train_length", 84))
            model_kwargs = dict(base.pop("model_kwargs", {}))
            if base:
                raise ValueError(f"unknown Darts base_args: {', '.join(sorted(base))}")
            model_kwargs[spec.parameter] = value
            complete = _signal(seed, repeat, train_length + h)
            train = complete[:train_length]
            actual = complete[train_length:]
            series = time_series.from_values(train.astype(np.float64))
            model = model_class(**model_kwargs)
            model.fit(series)
            forecast = model.predict(h)
            prediction = np.asarray(forecast.values(copy=False), dtype=float).reshape(-1)
            if prediction.shape != actual.shape:
                raise RuntimeError(
                    f"prediction shape {prediction.shape} does not match actual {actual.shape}"
                )
            if not np.isfinite(prediction).all():
                raise RuntimeError("prediction contains NaN/Inf")
            metric = float(np.mean(np.abs(prediction - actual) <= 1.0))
            return ProbeRunObservation(
                accepted=True,
                success=True,
                finite=True,
                output_shape=tuple(int(x) for x in forecast.values(copy=False).shape),
                prediction_sha256=_prediction_sha(prediction),
                observables={"metric": metric},
                runtime_seconds=time.perf_counter() - started,
                metadata={
                    "adapter": type(self).__name__,
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


class SktimeParameterAdapter:
    """Probe sktime NaiveForecaster constructor arguments with real predictions."""

    library = "sktime"

    def _imports(self) -> type[Any]:
        from sktime.forecasting.naive import NaiveForecaster  # type: ignore[import-untyped]

        return NaiveForecaster

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        try:
            model_class = self._imports()
        except ImportError as exc:
            return False, f"sktime unavailable: {exc}"
        if spec.model != "NaiveForecaster":
            return False, f"unsupported sktime model: {spec.model}"
        if spec.scope not in {ParameterScope.AUTO, ParameterScope.MODEL_CONSTRUCTOR}:
            return False, "sktime adapter probes NaiveForecaster constructor arguments"
        if spec.parameter not in inspect.signature(model_class).parameters:
            return False, f"{spec.parameter!r} is not in NaiveForecaster constructor"
        if spec.expected_surface in {EffectSurface.TRIAL_COUNT, EffectSurface.HISTORY}:
            return False, f"{spec.expected_surface.value} is not exposed by sktime adapter"
        return True, None

    def run(
        self,
        spec: ParameterProbeSpec,
        value: Any,
        seed: int,
        repeat: int,
    ) -> ProbeRunObservation:
        started = time.perf_counter()
        try:
            model_class = self._imports()
            base = dict(spec.base_args)
            h = int(base.pop("h", 7))
            train_length = int(base.pop("train_length", 84))
            sp = int(base.pop("sp", 1))
            model_kwargs = dict(base.pop("model_kwargs", {}))
            if base:
                raise ValueError(f"unknown sktime base_args: {', '.join(sorted(base))}")
            model_kwargs[spec.parameter] = value
            if "sp" in inspect.signature(model_class).parameters:
                model_kwargs.setdefault("sp", sp)
            complete = _signal(seed, repeat, train_length + h)
            train = pd.Series(complete[:train_length], index=pd.RangeIndex(train_length))
            actual = complete[train_length:]
            model = model_class(**model_kwargs)
            model.fit(train)
            fh = np.arange(1, h + 1, dtype=int)
            prediction_obj = model.predict(fh=fh)
            prediction = np.asarray(prediction_obj, dtype=float).reshape(-1)
            if prediction.shape != actual.shape:
                raise RuntimeError(
                    f"prediction shape {prediction.shape} does not match actual {actual.shape}"
                )
            if not np.isfinite(prediction).all():
                raise RuntimeError("prediction contains NaN/Inf")
            metric = float(np.mean(np.abs(prediction - actual) <= 1.0))
            return ProbeRunObservation(
                accepted=True,
                success=True,
                finite=True,
                output_shape=tuple(int(x) for x in prediction.shape),
                prediction_sha256=_prediction_sha(prediction),
                observables={"metric": metric},
                runtime_seconds=time.perf_counter() - started,
                metadata={
                    "adapter": type(self).__name__,
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


class GluonTSParameterAdapter:
    """Probe GluonTS SeasonalNaivePredictor arguments with real predictions."""

    library = "gluonts"

    def _imports(self) -> tuple[type[Any], type[Any]]:
        from gluonts.dataset.common import ListDataset  # type: ignore[import-untyped]
        from gluonts.model.seasonal_naive import (  # type: ignore[import-untyped]
            SeasonalNaivePredictor,
        )

        return ListDataset, SeasonalNaivePredictor

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        try:
            _, model_class = self._imports()
        except ImportError as exc:
            return False, f"GluonTS unavailable: {exc}"
        if spec.model != "SeasonalNaivePredictor":
            return False, f"unsupported GluonTS model: {spec.model}"
        if spec.scope not in {ParameterScope.AUTO, ParameterScope.MODEL_CONSTRUCTOR}:
            return False, "GluonTS adapter probes SeasonalNaivePredictor constructor arguments"
        if spec.parameter not in inspect.signature(model_class).parameters:
            return False, f"{spec.parameter!r} is not in SeasonalNaivePredictor constructor"
        if spec.expected_surface in {EffectSurface.TRIAL_COUNT, EffectSurface.HISTORY}:
            return False, f"{spec.expected_surface.value} is not exposed by GluonTS adapter"
        return True, None

    def run(
        self,
        spec: ParameterProbeSpec,
        value: Any,
        seed: int,
        repeat: int,
    ) -> ProbeRunObservation:
        started = time.perf_counter()
        try:
            list_dataset, model_class = self._imports()
            base = dict(spec.base_args)
            h = int(base.pop("h", 7))
            train_length = int(base.pop("train_length", 84))
            freq = str(base.pop("freq", "D"))
            model_kwargs = dict(base.pop("model_kwargs", {}))
            if base:
                raise ValueError(f"unknown GluonTS base_args: {', '.join(sorted(base))}")
            model_kwargs.setdefault("prediction_length", h)
            model_kwargs[spec.parameter] = value
            complete = _signal(seed, repeat, train_length + h)
            train = complete[:train_length]
            actual = complete[train_length:]
            dataset = list_dataset(
                [{"start": pd.Period("2000-01-01", freq=freq), "target": train}],
                freq=freq,
            )
            predictor = model_class(**model_kwargs)
            forecast = next(iter(predictor.predict(dataset)))
            prediction = np.asarray(forecast.mean, dtype=float).reshape(-1)
            if prediction.shape != actual.shape:
                raise RuntimeError(
                    f"prediction shape {prediction.shape} does not match actual {actual.shape}"
                )
            if not np.isfinite(prediction).all():
                raise RuntimeError("prediction contains NaN/Inf")
            metric = float(np.mean(np.abs(prediction - actual) <= 1.0))
            return ProbeRunObservation(
                accepted=True,
                success=True,
                finite=True,
                output_shape=tuple(int(x) for x in prediction.shape),
                prediction_sha256=_prediction_sha(prediction),
                observables={"metric": metric},
                runtime_seconds=time.perf_counter() - started,
                metadata={
                    "adapter": type(self).__name__,
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


class Toto2ParameterAdapter:
    """Probe Toto2 request parameters through the real checkpoint runtime."""

    library = "toto2"

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        if spec.model not in {"Toto2Model", "toto-2.0-4m"}:
            return False, f"unsupported Toto2 model: {spec.model}"
        if spec.parameter != "context_length":
            return False, "Toto2 Phase 5B currently certifies context_length"
        if spec.scope not in {ParameterScope.AUTO, ParameterScope.PREDICT}:
            return False, "Toto2 context_length is a predict/request parameter"
        if spec.expected_surface is not EffectSurface.HISTORY:
            return False, "Toto2 context_length must be observed on the actual input history surface"
        return True, None

    @staticmethod
    def _history(seed: int, repeat: int, length: int = 512) -> list[dict[str, float]]:
        rng = np.random.default_rng(seed + repeat * 100_003)
        t = np.arange(length, dtype=float)
        values = 8.0 + 2.0 * np.sin(t / 9.0) + 0.5 * np.cos(t / 4.0)
        values += rng.normal(0.0, 0.005, size=length)
        return [{"n1": float(value)} for value in values]

    def run(
        self,
        spec: ParameterProbeSpec,
        value: Any,
        seed: int,
        repeat: int,
    ) -> ProbeRunObservation:
        started = time.perf_counter()
        try:
            from loto.adapters.toto2_4m.contracts import (  # local import keeps core portable
                Toto2ProviderRequest,
            )
            from loto.toto2_campaign.runtime_executor import forecast_prepared, prepare_runtime

            base = dict(spec.base_args)
            snapshot_path = Path(str(base.pop("snapshot_path"))).expanduser().resolve()
            prediction_length = int(base.pop("prediction_length", 1))
            decode_block_size = int(base.pop("decode_block_size", 32))
            device = str(base.pop("device", "cuda"))
            if base:
                raise ValueError(f"unknown Toto2 base_args: {', '.join(sorted(base))}")
            context_length = int(value)
            history = self._history(seed, repeat)
            request = Toto2ProviderRequest(
                run_id=f"phase5b-toto2-c{context_length}-s{seed}-r{repeat}",
                game_geometry={
                    "game_id": "phase5b_synthetic",
                    "position_count": 1,
                    "candidate_min": 0,
                    "candidate_max": 20,
                    "strictly_increasing": False,
                },
                series_layout="position_univariate",
                position_columns=["n1"],
                history=history,
                timestamps=list(range(1, len(history) + 1)),
                context_length=context_length,
                prediction_length=prediction_length,
                decode_block_size=decode_block_size,
                device=device,
                seed=seed,
                snapshot_path=str(snapshot_path),
            )
            prepared = prepare_runtime(request, snapshot_path)
            native_output, runtime_evidence, artifact = forecast_prepared(request, prepared)
            input_shape = tuple(int(x) for x in artifact["input_shape"])
            observed_history = int(input_shape[-1])
            finite = bool(np.isfinite(native_output).all())
            if not finite:
                raise RuntimeError("native output contains NaN/Inf")
            if observed_history != context_length:
                raise RuntimeError(
                    f"effective context mismatch: expected {context_length}, got {observed_history}"
                )
            if device == "cuda":
                if runtime_evidence.cpu_fallback:
                    raise RuntimeError("CUDA request fell back to CPU")
                if runtime_evidence.peak_vram_bytes <= 0:
                    raise RuntimeError("CUDA execution has no positive peak VRAM evidence")
                if not runtime_evidence.execution_device.startswith("cuda"):
                    raise RuntimeError(
                        f"unexpected execution device: {runtime_evidence.execution_device}"
                    )
            return ProbeRunObservation(
                accepted=True,
                success=True,
                finite=True,
                output_shape=tuple(int(x) for x in native_output.shape),
                prediction_sha256=_prediction_sha(native_output),
                observables={"history": observed_history},
                runtime_seconds=time.perf_counter() - started,
                metadata={
                    "adapter": type(self).__name__,
                    "device": runtime_evidence.execution_device,
                    "peak_vram_bytes": str(runtime_evidence.peak_vram_bytes),
                    "input_shape": str(input_shape),
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


def register_extended_adapters(registry: Any) -> None:
    """Register Phase 5B adapters without importing optional libraries eagerly."""

    registry.register(DartsParameterAdapter())
    registry.register(SktimeParameterAdapter())
    registry.register(GluonTSParameterAdapter())
    registry.register(Toto2ParameterAdapter(), "toto")
