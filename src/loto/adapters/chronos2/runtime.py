from __future__ import annotations

import importlib.metadata
import math
import os
import subprocess
from collections.abc import Callable
from typing import Any

import pandas as pd

from .contracts import (
    ArgumentLedgerEntry,
    ArgumentStatus,
    Chronos2RequestV2,
    Chronos2ResponseV2,
    GPUProcessEvidence,
    PredictionIndexEntry,
    RuntimeEvidence,
    SeriesLayout,
)
from .geometry import CompiledChronosInput, compile_chronos_input
from .manifest import CHRONOS_PACKAGE_VERSION

PipelineLoader = Callable[[Chronos2RequestV2], Any]


def resolve_effective_arguments(
    request: Chronos2RequestV2,
) -> tuple[dict[str, Any], tuple[ArgumentLedgerEntry, ...], tuple[str, ...]]:
    history_length = len(request.history)
    warnings: list[str] = []
    effective_context = min(request.context_length, history_length)
    context_status = ArgumentStatus.ACCEPTED
    context_reason = None
    if request.context_length > history_length:
        context_status = ArgumentStatus.NOT_APPLICABLE
        context_reason = (
            "requested context exceeds available history; effective context is truncated"
        )
        warnings.append("CONTEXT_LENGTH_EXCEEDS_HISTORY")
    effective = {
        "context_length": effective_context,
        "prediction_length": request.prediction_length,
        "quantile_levels": list(request.quantile_levels),
        "cross_learning": request.cross_learning,
        "batch_size": request.batch_size,
        "device": request.device.value,
        "dtype": request.dtype.value,
        "attention_implementation": request.attention_implementation.value,
        "seed": request.seed,
        "series_layout": request.series_layout.value,
    }
    ledger = (
        ArgumentLedgerEntry(
            argument="context_length",
            requested_value=request.context_length,
            effective_value=effective_context,
            status=context_status,
            reason=context_reason,
        ),
        ArgumentLedgerEntry(
            argument="prediction_length",
            requested_value=request.prediction_length,
            effective_value=request.prediction_length,
            status=ArgumentStatus.ACCEPTED,
        ),
        ArgumentLedgerEntry(
            argument="quantile_levels",
            requested_value=list(request.quantile_levels),
            effective_value=list(request.quantile_levels),
            status=ArgumentStatus.ACCEPTED,
        ),
        ArgumentLedgerEntry(
            argument="cross_learning",
            requested_value=request.cross_learning,
            effective_value=request.cross_learning,
            status=ArgumentStatus.ACCEPTED,
        ),
        ArgumentLedgerEntry(
            argument="attention_implementation",
            requested_value=request.attention_implementation.value,
            effective_value=request.attention_implementation.value,
            status=ArgumentStatus.ACCEPTED,
        ),
    )
    return effective, ledger, tuple(warnings)


def _default_pipeline_loader(request: Chronos2RequestV2) -> Any:
    import torch
    from chronos import Chronos2Pipeline

    dtype = torch.float32 if request.dtype.value == "float32" else torch.bfloat16
    model_source = request.snapshot_path or request.repo_id
    kwargs: dict[str, Any] = {
        "device_map": request.device.value,
        "torch_dtype": dtype,
        "local_files_only": True,
        "attn_implementation": request.attention_implementation.value,
    }
    if request.snapshot_path is None:
        kwargs["revision"] = request.revision
    return Chronos2Pipeline.from_pretrained(model_source, **kwargs)


def _model_device(pipeline: Any) -> str:
    model = getattr(pipeline, "model", getattr(pipeline, "inner_model", None))
    if model is None:
        return "unknown"
    try:
        return str(next(model.parameters()).device)
    except (StopIteration, AttributeError):
        return str(getattr(model, "device", "unknown"))


def _cuda_memory() -> tuple[int | None, int | None, int | None]:
    try:
        import torch

        if not torch.cuda.is_available():
            return None, None, None
        return (
            int(torch.cuda.memory_allocated()),
            int(torch.cuda.max_memory_allocated()),
            int(torch.cuda.memory_allocated()),
        )
    except Exception:
        return None, None, None


def _nvidia_process_evidence(pid: int) -> tuple[str | None, bool | None]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,gpu_uuid",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None, None
    if completed.returncode != 0:
        return None, None
    for line in completed.stdout.splitlines():
        fields = [field.strip() for field in line.split(",", 1)]
        if len(fields) == 2 and fields[0] == str(pid):
            return fields[1], True
    return None, False


def _normalize_forecast(
    request: Chronos2RequestV2,
    compiled: CompiledChronosInput,
    forecast_df: pd.DataFrame,
) -> tuple[
    tuple[tuple[float, ...], ...],
    tuple[tuple[float, ...], ...],
    dict[str, tuple[tuple[float, ...], ...]],
    tuple[PredictionIndexEntry, ...],
]:
    required = {"item_id", "timestamp", "target_name", "predictions"}
    required.update(str(level) for level in request.quantile_levels)
    missing = sorted(required - set(forecast_df.columns))
    if missing:
        raise ValueError(f"forecast output is missing columns: {missing}")

    point_rows: list[tuple[float, ...]] = []
    median_rows: list[tuple[float, ...]] = []
    quantile_rows: dict[str, list[tuple[float, ...]]] = {
        str(level): [] for level in request.quantile_levels
    }
    index_entries: list[PredictionIndexEntry] = []

    for series_id in compiled.series_identity:
        if request.series_layout is SeriesLayout.POSITION_MULTIVARIATE:
            subset = forecast_df[forecast_df["target_name"] == series_id]
        else:
            subset = forecast_df[forecast_df["item_id"] == series_id]
        subset = subset.sort_values("timestamp", kind="stable")
        if len(subset) != request.prediction_length:
            raise ValueError(
                f"series {series_id!r} has {len(subset)} rows; expected {request.prediction_length}"
            )
        points = tuple(float(value) for value in subset["predictions"].tolist())
        if not all(math.isfinite(value) for value in points):
            raise ValueError("point forecast contains non-finite values")
        point_rows.append(points)

        q_values_by_level: list[tuple[float, ...]] = []
        for level in request.quantile_levels:
            key = str(level)
            values = tuple(float(value) for value in subset[key].tolist())
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"quantile {key} contains non-finite values")
            quantile_rows[key].append(values)
            q_values_by_level.append(values)
        for horizon_index in range(request.prediction_length):
            ordered = [values[horizon_index] for values in q_values_by_level]
            if ordered != sorted(ordered):
                raise ValueError(
                    f"quantile crossing detected for {series_id} horizon {horizon_index + 1}"
                )
        if 0.5 in request.quantile_levels:
            median_rows.append(q_values_by_level[request.quantile_levels.index(0.5)])
        else:
            median_rows.append(points)

        for horizon_index, (_, row) in enumerate(subset.iterrows(), start=1):
            index_entries.append(
                PredictionIndexEntry(
                    series_id=series_id,
                    target_name=series_id,
                    horizon_step=horizon_index,
                    timestamp=str(pd.Timestamp(row["timestamp"]).isoformat()),
                )
            )

    return (
        tuple(point_rows),
        tuple(median_rows),
        {key: tuple(values) for key, values in quantile_rows.items()},
        tuple(index_entries),
    )


def run_prediction(
    request: Chronos2RequestV2,
    *,
    pipeline_loader: PipelineLoader | None = None,
) -> Chronos2ResponseV2:
    effective, ledger, warnings = resolve_effective_arguments(request)
    compiled = compile_chronos_input(request)
    loader = pipeline_loader or _default_pipeline_loader
    before, _, _ = _cuda_memory()
    pipeline = loader(request)
    model_device = _model_device(pipeline)
    cpu_fallback = request.device.value == "cuda" and not model_device.startswith("cuda")
    if cpu_fallback:
        raise RuntimeError(f"model CPU fallback detected: {model_device}")

    forecast_df = pipeline.predict_df(
        compiled.context_df,
        future_df=compiled.future_df,
        id_column="item_id",
        timestamp_column="timestamp",
        target=compiled.target,
        prediction_length=request.prediction_length,
        quantile_levels=list(request.quantile_levels),
        batch_size=request.batch_size,
        context_length=effective["context_length"],
        cross_learning=request.cross_learning,
        validate_inputs=True,
        freq="D",
    )
    point, median, quantiles, prediction_index = _normalize_forecast(request, compiled, forecast_df)
    _, peak, after = _cuda_memory()
    pid = os.getpid()
    gpu_uuid, process_match = _nvidia_process_evidence(pid)
    package_version = importlib.metadata.version("chronos-forecasting")
    if package_version != CHRONOS_PACKAGE_VERSION:
        raise RuntimeError(
            f"chronos-forecasting version mismatch: {package_version} != {CHRONOS_PACKAGE_VERSION}"
        )
    response_warnings = list(warnings)
    response_warnings.append("CHRONOS2_2_3_1_POINT_IS_MEDIAN_NOT_ARITHMETIC_MEAN")
    return Chronos2ResponseV2(
        status="OK",
        run_id=request.run_id,
        operation=request.operation,
        model_identity={
            "model_id": request.model_id,
            "repo_id": request.repo_id,
            "revision": request.revision,
            "package_version": package_version,
        },
        effective_arguments={
            **effective,
            "source_history_sha256": compiled.source_history_sha256,
            "compiled_input_sha256": compiled.compiled_input_sha256,
        },
        argument_ledger=ledger,
        point_forecast=point,
        mean_forecast=(),
        median_forecast=median,
        quantiles=quantiles,
        prediction_index=prediction_index,
        series_identity=compiled.series_identity,
        runtime_evidence=RuntimeEvidence(
            parent_pid=request.parent_pid,
            provider_pid=pid,
            package_version=package_version,
            requested_device=request.device,
            model_parameter_device=model_device,
            dtype=request.dtype,
            attention_implementation=request.attention_implementation,
            cpu_fallback=False,
            finite=True,
            shape_verified=True,
            quantile_monotonicity_verified=True,
            vram_before_bytes=before,
            vram_peak_bytes=peak,
            vram_after_bytes=after,
            gpu_uuid=gpu_uuid,
            nvidia_smi_process_match=process_match,
        ),
        gpu_evidence=GPUProcessEvidence(
            gpu_uuid=gpu_uuid,
            pid=pid if request.device.value == "cuda" else None,
            process_match=process_match,
            vram_before_bytes=before,
            vram_peak_bytes=peak,
            vram_after_bytes=after,
        ),
        warnings=tuple(response_warnings),
    )
