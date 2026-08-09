from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from loto.adapters.autogluon.contracts import (
    DeviceRequest,
    ExecutionMode,
    ProviderOperation,
    ProviderRequestV2,
    ProviderResponseV2,
)
from loto.adapters.autogluon.inventory import TARGET_AUTOGLUON_VERSION
from loto.adapters.autogluon.provenance import canonical_sha256


class AutoGluonSharedContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AutoGluonGameProfile:
    game_id: str
    position_count: int
    candidate_min: int
    candidate_max: int
    allow_duplicates: bool
    sort_policy: str


@dataclass(frozen=True, slots=True)
class AutoGluonWorkerResult:
    position_values: tuple[float, ...]
    metadata: dict[str, Any]


AUTOGLUON_GAME_PROFILES: dict[str, AutoGluonGameProfile] = {
    "numbers3": AutoGluonGameProfile("numbers3", 3, 0, 9, True, "preserve"),
    "numbers4": AutoGluonGameProfile("numbers4", 4, 0, 9, True, "preserve"),
    "miniloto": AutoGluonGameProfile("miniloto", 5, 1, 31, False, "ascending"),
    "loto6": AutoGluonGameProfile("loto6", 6, 1, 43, False, "ascending"),
    "loto7": AutoGluonGameProfile("loto7", 7, 1, 37, False, "ascending"),
}

_GAME_ALIASES = {
    "numbers_3": "numbers3",
    "numbers-3": "numbers3",
    "numbers_4": "numbers4",
    "numbers-4": "numbers4",
    "mini_loto": "miniloto",
    "mini-loto": "miniloto",
    "mini loto": "miniloto",
    "loto_6": "loto6",
    "loto-6": "loto6",
    "loto_7": "loto7",
    "loto-7": "loto7",
}
_POSITION_COUNT_TO_GAME = {
    profile.position_count: game_id for game_id, profile in AUTOGLUON_GAME_PROFILES.items()
}

AUTOGLUON_CONCURRENCY_LIMITS = {
    "outer_workers": 8,
    "max_autogluon_jobs": 2,
    "max_gpu_jobs": 1,
}


def _canonical_game_id(value: str) -> str:
    normalized = value.strip().lower()
    return _GAME_ALIASES.get(normalized, normalized)


def resolve_game_profile(
    position_columns: tuple[str, ...] | list[str],
    *,
    game_id: str | None = None,
) -> AutoGluonGameProfile:
    columns = tuple(position_columns)
    if not columns:
        raise AutoGluonSharedContractError("GAME_GEOMETRY_MISSING", "position columns are empty")
    if game_id is None:
        resolved_id = _POSITION_COUNT_TO_GAME.get(len(columns))
        if resolved_id is None:
            raise AutoGluonSharedContractError(
                "GAME_GEOMETRY_UNSUPPORTED",
                f"cannot infer a supported game from {len(columns)} position columns",
            )
    else:
        resolved_id = _canonical_game_id(game_id)
    profile = AUTOGLUON_GAME_PROFILES.get(resolved_id)
    if profile is None:
        raise AutoGluonSharedContractError(
            "GAME_GEOMETRY_UNSUPPORTED",
            f"unsupported AutoGluon game_id={game_id!r}",
        )
    if len(columns) != profile.position_count:
        raise AutoGluonSharedContractError(
            "GAME_GEOMETRY_POSITION_MISMATCH",
            f"game {profile.game_id!r} requires {profile.position_count} positions, "
            f"got {len(columns)}",
        )
    return profile


def resolve_concurrency_limits(params: dict[str, Any]) -> dict[str, int]:
    resolved = dict(AUTOGLUON_CONCURRENCY_LIMITS)
    for name, expected in AUTOGLUON_CONCURRENCY_LIMITS.items():
        if name not in params:
            continue
        actual = int(params[name])
        if actual != expected:
            raise AutoGluonSharedContractError(
                "AUTOGLUON_CONCURRENCY_CONTRACT_MISMATCH",
                f"{name} must remain {expected}, got {actual}",
            )
    return resolved


def _model_ids(params: dict[str, Any]) -> tuple[str, ...]:
    raw = params.get("model_ids")
    if raw is None and params.get("model_id") is not None:
        raw = (params["model_id"],)
    if raw is None:
        return ()
    values: tuple[str, ...]
    if isinstance(raw, str):
        values = (raw,)
    else:
        values = tuple(str(value) for value in raw)
    values = tuple(value for value in values if value)
    if "autogluon-timeseries" in values:
        raise AutoGluonSharedContractError(
            "UMBRELLA_MODEL_ID_NOT_EXECUTABLE",
            "'autogluon-timeseries' is the shared provider identity, not an AutoGluon model alias",
        )
    if len(set(values)) != len(values):
        raise AutoGluonSharedContractError("MODEL_IDS_NOT_UNIQUE", "model_ids must be unique")
    return values


def _execution_mode(params: dict[str, Any], model_ids: tuple[str, ...]) -> ExecutionMode:
    requested = params.get("execution_mode")
    if requested is not None:
        try:
            return ExecutionMode(str(requested))
        except ValueError as exc:
            raise AutoGluonSharedContractError(
                "EXECUTION_MODE_UNSUPPORTED",
                f"unsupported AutoGluon execution_mode={requested!r}",
            ) from exc
    if params.get("hyperparameter_tune_kwargs") is not None:
        return ExecutionMode.HPO_SINGLE_MODEL
    if len(model_ids) > 1:
        return ExecutionMode.EXPLICIT_MULTI_MODEL
    if len(model_ids) == 1:
        return ExecutionMode.EXPLICIT_SINGLE_MODEL
    return ExecutionMode.PRESET_AUTOML


def _worker_run_id(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"autogluon-worker-{hashlib.sha256(encoded).hexdigest()[:24]}"


def build_autogluon_provider_request(
    history: pd.DataFrame,
    *,
    position_columns: tuple[str, ...] | list[str],
    params: dict[str, Any],
    requested_device: str,
    artifact_dir: str | Path,
) -> dict[str, Any]:
    columns = tuple(position_columns)
    profile = resolve_game_profile(columns, game_id=params.get("game_id"))
    resolve_concurrency_limits(params)
    required = ["draw_no", "draw_date", *columns]
    missing = [column for column in required if column not in history.columns]
    if missing:
        raise AutoGluonSharedContractError(
            "WORKER_HISTORY_COLUMNS_MISSING",
            f"history is missing required AutoGluon columns: {missing}",
        )
    frame = history[required].copy()
    frame["draw_date"] = frame["draw_date"].astype(str)
    records = frame.to_dict(orient="records")

    model_ids = _model_ids(params)
    mode = _execution_mode(params, model_ids)
    horizon = int(params.get("prediction_length", 1))
    if horizon != 1:
        raise AutoGluonSharedContractError(
            "WORKER_HORIZON_UNSUPPORTED",
            f"PositionSeriesWorker currently supports AutoGluon prediction_length=1, got {horizon}",
        )
    seed = int(params.get("autogluon_seed", 1))
    if mode in {ExecutionMode.PRESET_AUTOML, ExecutionMode.HPO_SINGLE_MODEL} and seed != 1:
        raise AutoGluonSharedContractError(
            "AUTO_SEARCH_SEED_MUST_BE_ONE",
            f"AutoGluon Auto/HPO execution must use seed=1, got {seed}",
        )

    try:
        device = DeviceRequest(requested_device)
    except ValueError as exc:
        raise AutoGluonSharedContractError(
            "DEVICE_REQUEST_UNSUPPORTED",
            f"unsupported requested_device={requested_device!r}",
        ) from exc

    operation_raw = str(params.get("operation", ProviderOperation.FIT_PREDICT_SAVE.value))
    try:
        operation = ProviderOperation(operation_raw)
    except ValueError as exc:
        raise AutoGluonSharedContractError(
            "OPERATION_UNSUPPORTED",
            f"unsupported AutoGluon operation={operation_raw!r}",
        ) from exc
    if operation not in {ProviderOperation.FIT_PREDICT_SAVE, ProviderOperation.LOAD_PREDICT}:
        raise AutoGluonSharedContractError(
            "WORKER_OPERATION_UNSUPPORTED",
            f"PositionSeriesWorker does not expose AutoGluon operation={operation.value!r}",
        )

    identity_payload = {
        "operation": operation.value,
        "game_id": profile.game_id,
        "position_columns": columns,
        "records": records,
        "model_ids": model_ids,
        "execution_mode": mode.value,
        "seed": seed,
        "artifact_dir": str(Path(artifact_dir).resolve()),
    }
    quantile_levels = tuple(
        float(value) for value in params.get("quantile_levels", (0.1, 0.5, 0.9))
    )
    request = ProviderRequestV2.model_validate(
        {
            "run_id": _worker_run_id(identity_payload),
            "operation": operation,
            "execution_mode": mode,
            "model_ids": model_ids,
            "artifact_dir": str(Path(artifact_dir).resolve()),
            "history": tuple(records),
            "geometry": {
                "game_id": profile.game_id,
                "position_columns": columns,
                "candidate_min": profile.candidate_min,
                "candidate_max": profile.candidate_max,
                "selection_count": profile.position_count,
                "horizon": horizon,
                "allow_duplicates": profile.allow_duplicates,
                "sort_policy": profile.sort_policy,
            },
            "predictor": {
                "target": "target",
                "prediction_length": horizon,
                "freq": "D",
                "eval_metric": str(params.get("eval_metric", "MAE")),
                "quantile_levels": quantile_levels,
                "cache_predictions": bool(params.get("cache_predictions", True)),
            },
            "fit": {
                "time_limit_seconds": int(
                    params.get("time_limit_seconds", params.get("time_limit", 120))
                ),
                "presets": params.get("presets", "fast_training"),
                "hyperparameters": params.get("hyperparameters"),
                "hyperparameter_tune_kwargs": params.get("hyperparameter_tune_kwargs"),
                "num_val_windows": params.get("num_val_windows", 1),
                "refit_every_n_windows": params.get("refit_every_n_windows", 1),
                "refit_full": bool(params.get("refit_full", False)),
                "enable_ensemble": bool(params.get("enable_ensemble", True)),
                "skip_model_selection": bool(params.get("skip_model_selection", False)),
            },
            "seed": seed,
            "requested_device": device,
        }
    )
    return request.model_dump(mode="json")


def _require_sha256(metadata: dict[str, Any], name: str) -> str:
    value = metadata.get(name)
    if not isinstance(value, str) or len(value) != 64:
        raise AutoGluonSharedContractError(
            "PROVIDER_HASH_EVIDENCE_MISSING",
            f"provider metadata.{name} must be a SHA-256 string",
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise AutoGluonSharedContractError(
            "PROVIDER_HASH_EVIDENCE_INVALID",
            f"provider metadata.{name} is not hexadecimal",
        ) from exc
    return value


def _validate_artifacts(request: ProviderRequestV2, response: ProviderResponseV2) -> None:
    assert request.artifact_dir is not None
    root = Path(request.artifact_dir).resolve()
    for name in ("provider_context", "execution_plan", "timeline_mapping"):
        raw = response.artifacts.get(name)
        if not raw:
            raise AutoGluonSharedContractError(
                "PROVIDER_ARTIFACT_MISSING",
                f"provider response is missing artifact reference {name!r}",
            )
        path = Path(raw).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise AutoGluonSharedContractError(
                "PROVIDER_ARTIFACT_PATH_ESCAPE",
                f"provider artifact {name!r} escapes artifact_dir: {path}",
            ) from exc
        if not path.is_file():
            raise AutoGluonSharedContractError(
                "PROVIDER_ARTIFACT_MISSING",
                f"provider artifact {name!r} does not exist: {path}",
            )


def _validate_runtime_evidence(request: ProviderRequestV2, response: ProviderResponseV2) -> None:
    evidence = response.runtime_evidence
    if evidence is None or evidence.pid is None or evidence.pid <= 0:
        raise AutoGluonSharedContractError(
            "PROVIDER_PID_EVIDENCE_MISSING",
            "provider runtime evidence must contain a positive PID",
        )
    if evidence.requested_device is not request.requested_device:
        raise AutoGluonSharedContractError(
            "PROVIDER_DEVICE_EVIDENCE_MISMATCH",
            "provider requested-device evidence does not match the worker request",
        )
    if request.requested_device is DeviceRequest.CPU:
        if evidence.resolved_device != "cpu" or evidence.cpu_fallback or evidence.gpu_used:
            raise AutoGluonSharedContractError(
                "CPU_EXECUTION_EVIDENCE_INVALID",
                "CPU request must resolve to CPU without fallback or GPU-use claims",
            )
        return
    if request.requested_device is DeviceRequest.CUDA:
        if evidence.resolved_device == "cpu":
            if not evidence.cpu_fallback or evidence.gpu_used:
                raise AutoGluonSharedContractError(
                    "CPU_FALLBACK_EVIDENCE_INVALID",
                    "CUDA-to-CPU fallback must be explicit and must not claim GPU use",
                )
            return
        if evidence.resolved_device != "cuda":
            raise AutoGluonSharedContractError(
                "GPU_EXECUTION_UNVERIFIED",
                "CUDA request did not resolve to a certified CUDA or explicit CPU-fallback state",
            )
        if (
            not evidence.gpu_used
            or evidence.evidence_status != "CERTIFIED"
            or evidence.vram_peak_bytes is None
            or evidence.vram_peak_bytes <= 0
        ):
            raise AutoGluonSharedContractError(
                "GPU_EXECUTION_UNVERIFIED",
                "GPU success requires gpu_used=true, CERTIFIED evidence, "
                "and positive VRAM evidence",
            )
        return
    if evidence.resolved_device == "unknown":
        raise AutoGluonSharedContractError(
            "AUTO_DEVICE_EXECUTION_UNVERIFIED",
            "auto device selection must resolve to an explicit CPU or certified CUDA state",
        )


def adapt_autogluon_provider_response(
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    *,
    params: dict[str, Any],
) -> AutoGluonWorkerResult:
    request = ProviderRequestV2.model_validate(request_payload)
    response = ProviderResponseV2.model_validate(response_payload)
    if response.run_id != request.run_id or response.operation is not request.operation:
        raise AutoGluonSharedContractError(
            "PROVIDER_RESPONSE_IDENTITY_MISMATCH",
            "provider response run_id/operation does not match the worker request",
        )
    if response.status != "OK":
        error = response.error
        code = error.code if error is not None else "PROVIDER_ERROR"
        message = (
            error.message if error is not None else "AutoGluon provider returned non-OK status"
        )
        raise AutoGluonSharedContractError(code, message)
    assert request.geometry is not None
    expected_items = tuple(
        f"position-{index}" for index in range(1, request.geometry.selection_count + 1)
    )
    if len(response.predictions) != len(expected_items):
        raise AutoGluonSharedContractError(
            "PREDICTION_SHAPE_MISMATCH",
            f"expected {len(expected_items)} horizon-1 predictions, "
            f"got {len(response.predictions)}",
        )
    by_item = {record.item_id: record for record in response.predictions}
    if tuple(sorted(by_item)) != tuple(sorted(expected_items)):
        raise AutoGluonSharedContractError(
            "PREDICTION_ITEM_ID_MISMATCH",
            f"expected item IDs {expected_items}, got {tuple(sorted(by_item))}",
        )
    expected_quantiles = {str(value) for value in request.predictor.quantile_levels}
    values: list[float] = []
    for item_id in expected_items:
        record = by_item[item_id]
        if record.horizon_step != 1 or not math.isfinite(record.mean):
            raise AutoGluonSharedContractError(
                "PREDICTION_VALUE_INVALID",
                f"prediction for {item_id!r} has invalid horizon or mean",
            )
        if set(record.quantiles) != expected_quantiles:
            raise AutoGluonSharedContractError(
                "PREDICTION_QUANTILE_MISMATCH",
                f"prediction for {item_id!r} has unexpected quantiles",
            )
        if not all(math.isfinite(value) for value in record.quantiles.values()):
            raise AutoGluonSharedContractError(
                "PREDICTION_VALUE_INVALID",
                f"prediction for {item_id!r} contains a non-finite quantile",
            )
        values.append(record.mean)

    metadata = dict(response.metadata)
    if metadata.get("library_version") != TARGET_AUTOGLUON_VERSION:
        raise AutoGluonSharedContractError(
            "RUNTIME_VERSION_MISMATCH",
            f"expected AutoGluon {TARGET_AUTOGLUON_VERSION}, "
            f"got {metadata.get('library_version')!r}",
        )
    if metadata.get("selected_model_ids") != list(request.model_ids):
        raise AutoGluonSharedContractError(
            "MODEL_IDENTITY_MISMATCH",
            "provider selected_model_ids does not match requested model_ids",
        )
    if request.model_ids and metadata.get("model_identity_verified") is not True:
        raise AutoGluonSharedContractError(
            "MODEL_IDENTITY_NOT_VERIFIED",
            "explicit AutoGluon model identity is not runtime-verified",
        )
    if metadata.get("prediction_shape") != [request.geometry.selection_count, 1]:
        raise AutoGluonSharedContractError(
            "PREDICTION_SHAPE_MISMATCH",
            "provider metadata prediction_shape does not match game geometry",
        )
    if metadata.get("finite") is not True:
        raise AutoGluonSharedContractError(
            "PREDICTION_VALUE_INVALID",
            "provider metadata does not certify finite predictions",
        )
    expected_request_sha = canonical_sha256(request.model_dump(mode="json"))
    if metadata.get("request_sha256") != expected_request_sha:
        raise AutoGluonSharedContractError(
            "REQUEST_HASH_MISMATCH",
            "provider request_sha256 does not match the worker request",
        )
    for name in (
        "request_sha256",
        "saved_context_sha256",
        "source_order_sha256",
        "timeline_mapping_sha256",
        "geometry_sha256",
        "plan_sha256",
    ):
        _require_sha256(metadata, name)
    _validate_artifacts(request, response)
    _validate_runtime_evidence(request, response)
    concurrency = resolve_concurrency_limits(params)
    evidence = response.runtime_evidence
    assert evidence is not None
    gpu_certified = bool(
        evidence.resolved_device == "cuda"
        and evidence.gpu_used
        and evidence.evidence_status == "CERTIFIED"
        and evidence.vram_peak_bytes is not None
        and evidence.vram_peak_bytes > 0
    )
    metadata.update(
        {
            "library": "autogluon",
            "protocol_version": 2,
            "provider_version": 2,
            "run_id": request.run_id,
            "operation": request.operation.value,
            "game_id": request.geometry.game_id,
            "position_columns": list(request.geometry.position_columns),
            "runtime_evidence": evidence.model_dump(mode="json"),
            "argument_ledger": [
                entry.model_dump(mode="json") for entry in response.argument_ledger
            ],
            "artifacts": dict(response.artifacts),
            "concurrency": concurrency,
            "gpu_certified": gpu_certified,
        }
    )
    return AutoGluonWorkerResult(position_values=tuple(values), metadata=metadata)


__all__ = [
    "AUTOGLUON_CONCURRENCY_LIMITS",
    "AUTOGLUON_GAME_PROFILES",
    "AutoGluonGameProfile",
    "AutoGluonSharedContractError",
    "AutoGluonWorkerResult",
    "adapt_autogluon_provider_response",
    "build_autogluon_provider_request",
    "resolve_concurrency_limits",
    "resolve_game_profile",
]
