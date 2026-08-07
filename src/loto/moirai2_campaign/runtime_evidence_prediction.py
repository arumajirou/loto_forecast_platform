from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from loto.moirai2_campaign.runtime_evidence_common import (
    EXPECTED_QUANTILE_KEYS,
    RuntimeEvidenceGateError,
    _SHA256_PATTERN,
    canonical_json_bytes,
    sha256_payload,
)

def _require_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise RuntimeEvidenceGateError(
            f"{message}: expected={expected!r} actual={actual!r}"
        )


def _require_true(value: Any, message: str) -> None:
    if value is not True:
        raise RuntimeEvidenceGateError(message)


def _finite_numbers(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise RuntimeEvidenceGateError("prediction contains a non-finite number")
        yield number
        return
    if isinstance(value, Mapping):
        for key in sorted(value):
            yield from _finite_numbers(value[key])
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _finite_numbers(item)
        return
    raise RuntimeEvidenceGateError(
        f"prediction contains unsupported value type: {type(value).__name__}"
    )


def _shape(value: Any) -> tuple[int, ...]:
    if isinstance(value, bool):
        raise RuntimeEvidenceGateError("boolean prediction value is invalid")
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise RuntimeEvidenceGateError("prediction contains a non-finite number")
        return ()
    if isinstance(value, list):
        if not value:
            return (0,)
        shapes = {_shape(item) for item in value}
        if len(shapes) != 1:
            raise RuntimeEvidenceGateError("prediction arrays are ragged")
        return (len(value), *next(iter(shapes)))
    raise RuntimeEvidenceGateError(
        f"prediction shape value is unsupported: {type(value).__name__}"
    )


def _flatten(value: Any) -> list[float]:
    return list(_finite_numbers(value))


def _quantile_key_sort(key: str) -> float:
    if not key.startswith("q"):
        raise RuntimeEvidenceGateError(f"invalid quantile key: {key}")
    try:
        return float(key[1:])
    except ValueError as exc:
        raise RuntimeEvidenceGateError(f"invalid quantile key: {key}") from exc


def validate_prediction_payload(response: dict[str, Any]) -> str:
    if response.get("status") != "OK":
        raise RuntimeEvidenceGateError("provider response status is not OK")
    quantiles = response.get("quantiles")
    if not isinstance(quantiles, dict):
        raise RuntimeEvidenceGateError("provider quantiles are missing")
    keys = tuple(sorted(quantiles, key=_quantile_key_sort))
    _require_equal(keys, EXPECTED_QUANTILE_KEYS, "native quantile keys differ")
    shapes = {_shape(quantiles[key]) for key in keys}
    if len(shapes) != 1:
        raise RuntimeEvidenceGateError("native quantile shapes differ")
    flattened = [_flatten(quantiles[key]) for key in keys]
    for index in range(len(flattened[0])):
        values = [items[index] for items in flattened]
        if values != sorted(values):
            raise RuntimeEvidenceGateError(
                f"native quantiles are not monotonic at flattened index {index}"
            )
    point = response.get("point_forecast")
    if _shape(point) != next(iter(shapes)):
        raise RuntimeEvidenceGateError("point forecast shape differs from quantiles")
    if canonical_json_bytes(point) != canonical_json_bytes(quantiles["q0.5"]):
        raise RuntimeEvidenceGateError("point forecast does not equal q0.5")
    identity = {
        "point_forecast": point,
        "quantiles": quantiles,
        "series_identity": response.get("series_identity"),
        "prediction_index": response.get("prediction_index"),
    }
    return sha256_payload(identity)


def _artifact_identity(response: dict[str, Any]) -> tuple[str, str, str]:
    artifact = response.get("artifact_reference")
    if not isinstance(artifact, dict):
        raise RuntimeEvidenceGateError("artifact_reference is missing")
    values = tuple(
        str(artifact.get(key, ""))
        for key in ("model_revision", "config_sha256", "weight_sha256")
    )
    if not values[0] or not all(_SHA256_PATTERN.fullmatch(value) for value in values[1:]):
        raise RuntimeEvidenceGateError("model artifact identity is invalid")
    return values


def _runtime(response: dict[str, Any]) -> dict[str, Any]:
    runtime = response.get("runtime_evidence")
    if not isinstance(runtime, dict):
        raise RuntimeEvidenceGateError("runtime_evidence is missing")
    return runtime


def _gpu(response: dict[str, Any]) -> dict[str, Any]:
    gpu = response.get("gpu_evidence")
    if not isinstance(gpu, dict):
        raise RuntimeEvidenceGateError("gpu_evidence is missing")
    return gpu


def validate_response_device(
    response: dict[str, Any],
    *,
    runtime_lane: str,
    requested_device: str,
) -> int:
    runtime = _runtime(response)
    gpu = _gpu(response)
    _require_equal(runtime.get("runtime_lane"), runtime_lane, "runtime lane differs")
    _require_equal(
        runtime.get("requested_device"),
        requested_device,
        "requested device differs",
    )
    _require_equal(
        runtime.get("execution_device"),
        requested_device,
        "execution device differs",
    )
    if bool(runtime.get("cpu_fallback")) or bool(gpu.get("cpu_fallback")):
        raise RuntimeEvidenceGateError("CPU fallback evidence is present")
    process_id = int(runtime.get("process_id", -1))
    if process_id < 1 or int(gpu.get("provider_pid", -2)) != process_id:
        raise RuntimeEvidenceGateError("provider PID evidence is inconsistent")
    effective = response.get("effective_arguments")
    if not isinstance(effective, dict):
        raise RuntimeEvidenceGateError("effective_arguments is missing")
    forward = effective.get("forward_device_evidence")
    if not isinstance(forward, dict):
        raise RuntimeEvidenceGateError("forward device evidence is missing")
    if int(forward.get("forward_call_count", 0)) < 1:
        raise RuntimeEvidenceGateError("no provider forward call was recorded")
    observed = [
        str(runtime.get("model_parameter_device", "")),
        str(effective.get("predictor_device", "")),
        *[str(item) for item in forward.get("input_tensor_devices", [])],
        *[str(item) for item in forward.get("output_tensor_devices", [])],
    ]
    if len(observed) < 4 or any(
        not value.startswith(requested_device) for value in observed
    ):
        raise RuntimeEvidenceGateError(
            f"observed tensor/module devices differ from {requested_device}: {observed}"
        )
    if requested_device == "cuda":
        if int(gpu.get("gpu_pid", -1)) != process_id:
            raise RuntimeEvidenceGateError("CUDA provider GPU PID differs")
        if int(gpu.get("peak_vram_bytes", 0)) <= 0:
            raise RuntimeEvidenceGateError("CUDA peak VRAM evidence is not positive")
    elif gpu.get("gpu_pid") is not None:
        raise RuntimeEvidenceGateError("CPU response reports a GPU PID")
    return process_id



