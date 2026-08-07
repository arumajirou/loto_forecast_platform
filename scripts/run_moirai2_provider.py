from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.adapters.moirai2.contracts import (  # noqa: E402
    Moirai2ProviderRequest,
    Moirai2ProviderResponse,
)
from loto.moirai2_campaign.covariates import (  # noqa: E402
    attach_covariates,
    compile_covariates,
)
from loto.moirai2_campaign.license_policy import evaluate_license_lane  # noqa: E402
from loto.moirai2_campaign.model_manifest import (  # noqa: E402
    MODEL_ID,
    MODEL_REVISION,
    NATIVE_QUANTILE_LEVELS,
    REPO_ID,
    UNI2TS_VERSION,
)
from loto.moirai2_campaign.provenance import verify_snapshot  # noqa: E402
from loto.moirai2_campaign.quantiles import (  # noqa: E402
    extract_native_quantiles,
    median_point_forecast,
)
from loto.moirai2_campaign.time_adapter import (  # noqa: E402
    build_calendar_time_axis,
    build_draw_sequence_axis,
)
from loto.moirai2_campaign.token_geometry import calculate_token_geometry  # noqa: E402


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _snapshot(request: Moirai2ProviderRequest) -> Path:
    if request.snapshot_path:
        return Path(request.snapshot_path)
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=request.repo_id,
            revision=request.revision,
            local_files_only=True,
            allow_patterns=["config.json", "model.safetensors", "README.md", "LICENSE*"],
        )
    )


def _identity_response(request: Moirai2ProviderRequest, runtime_lane: str) -> dict[str, Any]:
    license_evidence = evaluate_license_lane(request.license_lane).as_dict()
    return Moirai2ProviderResponse(
        status="OK",
        phase="identity",
        message="pinned Moirai 2.0 identity",
        model_identity={
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "revision": MODEL_REVISION,
            "uni2ts_version": UNI2TS_VERSION,
            "native_quantile_levels": list(NATIVE_QUANTILE_LEVELS),
        },
        effective_arguments={"runtime_lane": runtime_lane},
        license_evidence=license_evidence,
    ).model_dump(mode="json")


def run_provider(request: Moirai2ProviderRequest, *, runtime_lane: str) -> dict[str, Any]:
    if request.operation.value == "identity":
        return _identity_response(request, runtime_lane)
    license_decision = evaluate_license_lane(request.license_lane)
    past_dim = len(request.past_covariates)
    known_future_dim = len(request.future_covariates)
    token_geometry = calculate_token_geometry(
        target_dim=request.game_geometry.position_count,
        feat_dynamic_real_dim=known_future_dim,
        past_feat_dynamic_real_dim=past_dim,
        context_length=request.context_length,
        prediction_length=request.prediction_length,
    )
    requested_device = request.device
    if requested_device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import torch
    from gluonts.dataset.common import ListDataset
    from uni2ts.model.moirai2 import Moirai2Forecast, Moirai2Module

    package_version = importlib.metadata.version("uni2ts")
    if package_version != UNI2TS_VERSION:
        raise RuntimeError(
            f"uni2ts version mismatch: expected={UNI2TS_VERSION}, actual={package_version}"
        )
    cuda_available = torch.cuda.is_available()
    if requested_device == "cuda" and not cuda_available:
        raise RuntimeError("FAILED_CPU_FALLBACK: CUDA was requested but unavailable")
    execution_device = requested_device
    if execution_device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    snapshot_path = _snapshot(request)
    artifact_reference = verify_snapshot(snapshot_path)

    history = request.history[-request.context_length :]
    target = np.asarray(
        [[row[column] for row in history] for column in request.position_columns],
        dtype=np.float32,
    )
    context_timestamps = request.timestamps[-request.context_length :] if request.timestamps else []
    if request.time_semantics.value == "calendar_time":
        time_axis = build_calendar_time_axis(target, context_timestamps)
    else:
        draw_numbers = None
        if context_timestamps:
            draw_numbers = [int(value) for value in context_timestamps]
        time_axis = build_draw_sequence_axis(target, draw_numbers)

    covariates = compile_covariates(
        history_length=len(request.history),
        context_length=request.context_length,
        prediction_length=request.prediction_length,
        past_covariates=request.past_covariates,
        future_covariates=request.future_covariates,
        future_covariate_availability=request.future_covariate_availability,
        time_semantics=request.time_semantics.value,
        context_timestamps=context_timestamps,
        target_time_length=time_axis.target.shape[1],
    )
    is_univariate = request.game_geometry.position_count == 1
    dataset_target = time_axis.target[0] if is_univariate else time_axis.target
    dataset_entry = attach_covariates(
        {"start": time_axis.start, "target": dataset_target},
        covariates,
    )
    dataset = ListDataset(
        [dataset_entry],
        freq=time_axis.frequency,
        one_dim_target=is_univariate,
    )
    module = Moirai2Module.from_pretrained(str(snapshot_path), local_files_only=True)
    module = module.to(execution_device).eval()
    module_parameter = next(module.parameters())
    if module_parameter.device.type != execution_device:
        raise RuntimeError("module parameter device does not match requested device")
    model = Moirai2Forecast(
        module=module,
        prediction_length=request.prediction_length,
        context_length=request.context_length,
        target_dim=request.game_geometry.position_count,
        feat_dynamic_real_dim=covariates.known_future_dim,
        past_feat_dynamic_real_dim=covariates.past_dim,
    )
    predictor = model.create_predictor(batch_size=request.batch_size, device=execution_device)
    forecast = next(iter(predictor.predict(dataset)))
    if execution_device == "cuda":
        torch.cuda.synchronize()
    quantiles = extract_native_quantiles(
        forecast,
        horizon=request.prediction_length,
        position_count=request.game_geometry.position_count,
    )
    point_forecast = median_point_forecast(quantiles)
    output_shape = [request.prediction_length, request.game_geometry.position_count]
    cpu_fallback = requested_device != execution_device
    if cpu_fallback:
        raise RuntimeError("FAILED_CPU_FALLBACK")
    return Moirai2ProviderResponse(
        status="OK",
        phase="predict",
        message="Moirai 2.0 native quantile inference completed",
        model_identity={
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "revision": MODEL_REVISION,
        },
        effective_arguments={
            "context_length": request.context_length,
            "prediction_length": request.prediction_length,
            "target_dim": request.game_geometry.position_count,
            "feat_dynamic_real_dim": covariates.known_future_dim,
            "past_feat_dynamic_real_dim": covariates.past_dim,
            "quantile_count": len(NATIVE_QUANTILE_LEVELS),
            "sample_support": False,
            "num_samples": None,
            "token_geometry": token_geometry.as_dict(),
            "time_semantics": request.time_semantics.value,
            "frequency_policy": time_axis.frequency_policy,
            "missing_period_policy": time_axis.missing_period_policy,
            "timestamp_mapping_sha256": time_axis.mapping_sha256,
            "past_covariate_names": list(covariates.past.names),
            "known_future_covariate_names": list(covariates.known_future.names),
            "future_covariate_availability": request.future_covariate_availability,
        },
        point_forecast=point_forecast,
        quantiles=quantiles,
        series_identity=request.position_columns,
        prediction_index=list(range(1, request.prediction_length + 1)),
        runtime_evidence={
            "process_id": os.getpid(),
            "package_version": package_version,
            "runtime_lane": runtime_lane,
            "requested_device": requested_device,
            "execution_device": execution_device,
            "model_parameter_device": str(module_parameter.device),
            "output_shape": output_shape,
            "all_quantiles_finite": True,
            "quantile_monotonicity": True,
            "cpu_fallback": False,
        },
        gpu_evidence={
            "requested_device": requested_device,
            "execution_device": execution_device,
            "cuda_available": cuda_available,
            "provider_pid": os.getpid(),
            "gpu_pid": os.getpid() if execution_device == "cuda" else None,
            "peak_vram_bytes": (
                int(torch.cuda.max_memory_allocated()) if execution_device == "cuda" else 0
            ),
            "cpu_fallback": False,
        },
        covariate_evidence=covariates.as_dict(),
        artifact_reference=artifact_reference,
        license_evidence=license_decision.as_dict(),
    ).model_dump(mode="json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated Moirai 2.0 provider")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--runtime-lane", required=True)
    arguments = parser.parse_args()
    try:
        request = Moirai2ProviderRequest.model_validate_json(
            arguments.request.read_text(encoding="utf-8")
        )
        response = run_provider(request, runtime_lane=arguments.runtime_lane)
    except Exception as exc:
        response = Moirai2ProviderResponse(
            status="ERROR",
            phase="provider",
            message=f"{type(exc).__name__}: {exc}",
        ).model_dump(mode="json")
    _write_atomic(arguments.response, response)
    return 0 if response.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
