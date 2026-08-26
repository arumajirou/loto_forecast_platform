"""Dependency-minimal Toto2 parameter-effectiveness adapter.

This module intentionally avoids pandas and the general adapter registry so the
certified minimal Toto2 runtime can execute the probe without unrelated packages.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

import numpy as np

from .contracts import EffectSurface, ParameterProbeSpec, ParameterScope, ProbeRunObservation


def _prediction_sha(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.float64)
    payload = str(array.shape).encode("ascii") + array.tobytes()
    return hashlib.sha256(payload).hexdigest()


class Toto2MinimalParameterAdapter:
    library = "toto2"

    def supports(self, spec: ParameterProbeSpec) -> tuple[bool, str | None]:
        if spec.model not in {"Toto2Model", "toto-2.0-4m"}:
            return False, f"unsupported Toto2 model: {spec.model}"
        if spec.parameter != "context_length":
            return False, "Toto2 Phase 5B currently certifies context_length"
        if spec.scope not in {ParameterScope.AUTO, ParameterScope.PREDICT}:
            return False, "Toto2 context_length is a predict/request parameter"
        if spec.expected_surface is not EffectSurface.HISTORY:
            return False, "Toto2 context_length must use the actual input-history surface"
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
            from loto.adapters.toto2_4m.contracts import Toto2ProviderRequest
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
            native_output, evidence, artifact = forecast_prepared(request, prepared)
            input_shape = tuple(int(x) for x in artifact["input_shape"])
            observed_history = int(input_shape[-1])

            if observed_history != context_length:
                raise RuntimeError(
                    f"effective context mismatch: expected {context_length}, got {observed_history}"
                )
            if not np.isfinite(native_output).all():
                raise RuntimeError("native output contains NaN/Inf")
            if device == "cuda":
                if evidence.cpu_fallback:
                    raise RuntimeError("CUDA request fell back to CPU")
                if evidence.peak_vram_bytes <= 0:
                    raise RuntimeError("CUDA execution has no positive peak VRAM evidence")
                if not evidence.execution_device.startswith("cuda"):
                    raise RuntimeError(f"unexpected execution device: {evidence.execution_device}")

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
                    "execution_device": evidence.execution_device,
                    "model_device": evidence.model_device,
                    "output_device": evidence.output_device,
                    "peak_vram_bytes": evidence.peak_vram_bytes,
                    "cpu_fallback": evidence.cpu_fallback,
                    "input_shape": list(input_shape),
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
