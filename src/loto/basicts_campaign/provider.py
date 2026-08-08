from __future__ import annotations

import importlib.metadata
import json
import traceback
from pathlib import Path
from typing import Any

from .contracts import (
    EXPECTED_BASICTS_VERSION,
    BasicTSOperation,
    BasicTSProviderRequest,
    BasicTSProviderResponse,
    BasicTSStatus,
    ErrorEvidence,
)
from .dataset import compile_basic_ts_dataset
from .provenance import atomic_write_json, write_artifact_manifest
from .security import resolve_import_reference, validate_safe_config


def _identity() -> tuple[BasicTSStatus, bool, str | None, dict[str, Any]]:
    try:
        package_version = importlib.metadata.version("BasicTS")
        import basicts
    except (importlib.metadata.PackageNotFoundError, ImportError):
        return BasicTSStatus.UNAVAILABLE, False, None, {"reason": "BasicTS is not installed"}
    module_version = getattr(basicts, "__version__", None)
    status = (
        BasicTSStatus.PASS
        if package_version == EXPECTED_BASICTS_VERSION
        and module_version == EXPECTED_BASICTS_VERSION
        else BasicTSStatus.FAILED
    )
    return (
        status,
        True,
        package_version,
        {
            "distribution_version": package_version,
            "module_version": module_version,
            "expected_version": EXPECTED_BASICTS_VERSION,
        },
    )


def _construct_forward_save_load_smoke(
    request: BasicTSProviderRequest,
    artifact_dir: Path,
) -> tuple[str, dict[str, Any], list[str]]:
    if request.config is None:
        raise ValueError("config is required")
    package_version = importlib.metadata.version("BasicTS")
    if package_version != EXPECTED_BASICTS_VERSION:
        message = (
            "BasicTS version mismatch: "
            f"expected={EXPECTED_BASICTS_VERSION} actual={package_version}"
        )
        raise RuntimeError(message)

    import torch
    from basicts.configs import BasicTSForecastingConfig
    from basicts.configs.model_config import BasicTSModelConfig

    resolved = validate_safe_config(request.config, resolve=True)
    model_type = resolve_import_reference(request.config.model)
    model_config = BasicTSModelConfig(
        input_len=request.config.input_len,
        output_len=request.config.output_len,
        channels=request.config.channels,
    )
    cfg = BasicTSForecastingConfig(
        model=model_type,
        model_config=model_config,
        dataset_name="loto-contract-smoke",
        dataset_params={
            "dataset_name": "loto-contract-smoke",
            "input_len": request.config.input_len,
            "output_len": request.config.output_len,
            "local": True,
            "data_file_path": str(artifact_dir / "unused-dataset"),
            "memmap": False,
        },
        gpus=None,
        seed=request.config.seed,
        deterministic=True,
        eval_after_train=False,
        test_interval=None,
        num_epochs=1,
        num_steps=None,
        ckpt_save_dir=str(artifact_dir / "checkpoints"),
    )

    torch.manual_seed(request.config.seed)
    model = model_type(**model_config)
    model.eval()
    inputs = torch.arange(
        2 * request.config.input_len * request.config.channels,
        dtype=torch.float32,
    ).reshape(2, request.config.input_len, request.config.channels, 1)
    with torch.no_grad():
        before = model(inputs)
    if tuple(before.shape) != (
        2,
        request.config.output_len,
        request.config.channels,
        1,
    ):
        raise RuntimeError(f"unexpected prediction shape: {tuple(before.shape)}")
    if not torch.isfinite(before).all():
        raise RuntimeError("prediction contains NaN or Inf")

    model_path = artifact_dir / "tiny_linear_state.pt"
    torch.save(model.state_dict(), model_path)
    reloaded = model_type(**model_config)
    reloaded.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
    reloaded.eval()
    with torch.no_grad():
        after = reloaded(inputs)
    if not torch.equal(before, after):
        raise RuntimeError("save/load prediction equality failed")

    config_path = artifact_dir / "effective_config.json"
    atomic_write_json(config_path, json.loads(str(cfg)))
    return (
        package_version,
        {
            "resolved_imports": resolved,
            "basic_ts_config_md5": cfg.md5,
            "prediction_shape": list(before.shape),
            "prediction_finite": True,
            "save_load_prediction_equal": True,
            "device": "cpu",
            "training_executed": False,
            "smoke_scope": "config_construct_forward_save_load",
            "eval_after_train": cfg.eval_after_train,
            "test_interval": cfg.test_interval,
        },
        [model_path.name, config_path.name],
    )


def process_request(request: BasicTSProviderRequest) -> BasicTSProviderResponse:
    artifact_dir = Path(request.artifact_dir).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    package_version: str | None = None
    artifacts: list[str] = []
    try:
        if request.operation == BasicTSOperation.IDENTITY:
            status, actual_execution, package_version, evidence = _identity()
        elif request.operation == BasicTSOperation.VALIDATE_CONFIG:
            if request.config is None:
                raise ValueError("config is required")
            evidence = {
                "resolved_imports": validate_safe_config(request.config, resolve=False),
                "holdout_auto_evaluation_disabled": True,
                "cpu_only": True,
            }
            status, actual_execution = BasicTSStatus.PASS, False
        elif request.operation == BasicTSOperation.COMPILE_DATASET:
            if request.dataset is None:
                raise ValueError("dataset is required")
            evidence = compile_basic_ts_dataset(request.dataset, artifact_dir / "dataset")
            artifacts.extend(f"dataset/{path}" for path in evidence["artifacts"])
            status, actual_execution = BasicTSStatus.PASS, True
        elif request.operation == BasicTSOperation.CONSTRUCT_FORWARD_SAVE_LOAD_SMOKE:
            package_version, evidence, smoke_artifacts = _construct_forward_save_load_smoke(
                request,
                artifact_dir,
            )
            artifacts.extend(smoke_artifacts)
            status, actual_execution = BasicTSStatus.PASS, True
        else:
            raise ValueError(f"unsupported operation: {request.operation}")
        response = BasicTSProviderResponse(
            request_id=request.request_id,
            operation=request.operation,
            status=status,
            actual_execution=actual_execution,
            package_version=package_version,
            evidence=evidence,
            artifacts=artifacts,
        )
    except importlib.metadata.PackageNotFoundError as exc:
        response = BasicTSProviderResponse(
            request_id=request.request_id,
            operation=request.operation,
            status=BasicTSStatus.UNAVAILABLE,
            actual_execution=False,
            evidence={"reason": "BasicTS distribution is unavailable"},
            error=ErrorEvidence(
                phase="provider",
                exception_type=type(exc).__name__,
                message=str(exc),
                traceback=traceback.format_exc(),
            ),
        )
    except BaseException as exc:
        response = BasicTSProviderResponse(
            request_id=request.request_id,
            operation=request.operation,
            status=BasicTSStatus.FAILED,
            actual_execution=False,
            package_version=package_version,
            error=ErrorEvidence(
                phase="provider",
                exception_type=type(exc).__name__,
                message=str(exc),
                traceback=traceback.format_exc(),
            ),
        )

    response_path = artifact_dir / "response.json"
    atomic_write_json(response_path, response.model_dump(mode="json"))
    response.artifacts.append(response_path.name)
    manifest_path, checksum_path = write_artifact_manifest(artifact_dir)
    response.artifacts.extend([manifest_path.name, checksum_path.name])
    return response
