from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from loto.adapters.toto2_4m.contracts import RuntimeEvidence, Toto2ProviderRequest
from loto.toto2_campaign.model_manifest import (
    ARTIFACT_SHA256,
    ARTIFACT_SIZE_BYTES,
    CERTIFIED_CUDA_VERSION,
    CERTIFIED_PYTHON_SERIES,
    CERTIFIED_TORCH_VERSION_PREFIX,
    MODEL_CLASS,
    MODEL_PARAMETER_COUNT,
    MODEL_REVISION,
    NATIVE_QUANTILE_LEVELS,
    TOTO_2_VERSION,
    TOTO_MODELS_VERSION,
)


class RuntimeDependencyError(RuntimeError):
    pass


class SnapshotIntegrityError(RuntimeError):
    pass


class RuntimeExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotFileEvidence:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class PreparedRuntime:
    torch: Any
    model: Any
    target: Any
    inputs: dict[str, Any]
    device: Any
    model_device: str
    snapshot: dict[str, Any]
    versions: dict[str, str | None]
    vram_before_bytes: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_snapshot(snapshot_path: Path) -> dict[str, Any]:
    snapshot = snapshot_path.expanduser().resolve(strict=True)
    if not snapshot.is_dir():
        raise SnapshotIntegrityError(f"snapshot is not a directory: {snapshot}")
    if snapshot.name != MODEL_REVISION:
        raise SnapshotIntegrityError(
            f"snapshot revision mismatch: expected {MODEL_REVISION}, got {snapshot.name}"
        )
    files: dict[str, dict[str, object]] = {}
    for name, expected_digest in ARTIFACT_SHA256.items():
        path = snapshot / name
        if not path.is_file():
            raise SnapshotIntegrityError(f"required snapshot file missing: {name}")
        size = path.stat().st_size
        expected_size = ARTIFACT_SIZE_BYTES.get(name)
        if expected_size is not None and size != expected_size:
            raise SnapshotIntegrityError(
                f"snapshot size mismatch for {name}: expected {expected_size}, got {size}"
            )
        actual_digest = sha256_file(path)
        if actual_digest != expected_digest:
            raise SnapshotIntegrityError(
                f"snapshot SHA-256 mismatch for {name}: expected {expected_digest}, "
                f"got {actual_digest}"
            )
        files[name] = asdict(SnapshotFileEvidence(str(path), size, actual_digest))
    return {"snapshot_path": str(snapshot), "revision": MODEL_REVISION, "files": files}


def history_to_numpy(request: Toto2ProviderRequest) -> np.ndarray:
    if request.context_length not in {128, 256, 512}:
        raise RuntimeExecutionError("formal context_length must be 128, 256, or 512")
    if request.decode_block_size < 32 or request.decode_block_size % 32:
        raise RuntimeExecutionError("decode_block_size must be a positive multiple of 32")
    rows = request.history[-request.context_length :]
    values = [[float(row[column]) for row in rows] for column in request.position_columns]
    target = np.asarray(values, dtype=np.float32)[None, :, :]
    expected = (1, request.game_geometry.position_count, request.context_length)
    if target.shape != expected:
        raise RuntimeExecutionError(
            f"input shape mismatch: expected {expected}, got {target.shape}"
        )
    if not np.isfinite(target).all():
        raise RuntimeExecutionError("input contains non-finite values")
    return target


def _distribution_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeDependencyError(f"required distribution is missing: {name}") from exc


def load_runtime_dependencies() -> tuple[Any, type[Any], dict[str, str | None]]:
    python_version = platform.python_version()
    if not python_version.startswith(f"{CERTIFIED_PYTHON_SERIES}."):
        raise RuntimeDependencyError(
            f"Python {CERTIFIED_PYTHON_SERIES}.x required, got {python_version}"
        )
    try:
        import torch
        from toto2 import Toto2Model
    except ImportError as exc:
        raise RuntimeDependencyError(f"Toto runtime import failed: {exc}") from exc

    versions: dict[str, str | None] = {
        "python_version": python_version,
        "torch_version": str(torch.__version__),
        "torch_cuda_version": str(torch.version.cuda) if torch.version.cuda else None,
        "toto_2_version": _distribution_version("toto-2"),
        "toto_models_version": _distribution_version("toto-models"),
    }
    if versions["toto_2_version"] != TOTO_2_VERSION:
        raise RuntimeDependencyError("toto-2 version differs from the recorded runtime")
    if versions["toto_models_version"] != TOTO_MODELS_VERSION:
        raise RuntimeDependencyError("toto-models version differs from the recorded runtime")
    if not str(versions["torch_version"]).startswith(CERTIFIED_TORCH_VERSION_PREFIX):
        raise RuntimeDependencyError("torch version differs from the recorded runtime")
    return torch, Toto2Model, versions


@contextmanager
def offline_huggingface() -> Iterator[None]:
    names = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    previous = {name: os.environ.get(name) for name in names}
    os.environ.update({name: "1" for name in names})
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _resolve_device(
    request: Toto2ProviderRequest,
    torch: Any,
    versions: dict[str, str | None],
) -> Any:
    if request.device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeExecutionError("CUDA requested but torch.cuda.is_available() is false")
        if versions["torch_cuda_version"] != CERTIFIED_CUDA_VERSION:
            raise RuntimeDependencyError("CUDA runtime differs from the recorded runtime")
        return torch.device("cuda:0")
    return torch.device("cpu")


def _validate_model(model: Any) -> tuple[str, int]:
    if type(model).__name__ != MODEL_CLASS:
        raise RuntimeExecutionError(
            f"model class mismatch: expected {MODEL_CLASS}, got {type(model).__name__}"
        )
    parameter_count = sum(int(parameter.numel()) for parameter in model.parameters())
    if parameter_count != MODEL_PARAMETER_COUNT:
        raise RuntimeExecutionError(
            f"parameter count mismatch: expected {MODEL_PARAMETER_COUNT}, got {parameter_count}"
        )
    if int(getattr(model.config, "patch_size", -1)) != 32:
        raise RuntimeExecutionError("model patch_size is not 32")
    knots = tuple(round(float(value), 1) for value in model.output_head.knots)
    if knots != NATIVE_QUANTILE_LEVELS:
        raise RuntimeExecutionError("native model quantile levels differ from q0.1 through q0.9")
    return str(next(model.parameters()).device), parameter_count


def prepare_runtime(
    request: Toto2ProviderRequest,
    snapshot_path: Path,
    *,
    dependency_loader: Callable[[], tuple[Any, type[Any], dict[str, str | None]]] = (
        load_runtime_dependencies
    ),
) -> PreparedRuntime:
    snapshot = verify_snapshot(snapshot_path)
    torch, model_class, versions = dependency_loader()
    device = _resolve_device(request, torch, versions)
    target_numpy = history_to_numpy(request)
    if request.device == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
        vram_before = int(torch.cuda.memory_allocated(device))
    else:
        vram_before = 0
    torch.manual_seed(request.seed)
    if request.device == "cuda":
        torch.cuda.manual_seed_all(request.seed)
    with offline_huggingface():
        model = model_class.from_pretrained(snapshot["snapshot_path"])
    model = model.to(device).eval()
    model_device, _ = _validate_model(model)
    target = torch.as_tensor(target_numpy, dtype=torch.float32, device=device)
    inputs = {
        "target": target,
        "target_mask": torch.ones_like(target, dtype=torch.bool),
        "series_ids": torch.zeros(
            (1, request.game_geometry.position_count),
            dtype=torch.long,
            device=device,
        ),
    }
    return PreparedRuntime(
        torch=torch,
        model=model,
        target=target,
        inputs=inputs,
        device=device,
        model_device=model_device,
        snapshot=snapshot,
        versions=versions,
        vram_before_bytes=vram_before,
    )


def forecast_prepared(
    request: Toto2ProviderRequest,
    prepared: PreparedRuntime,
) -> tuple[np.ndarray, RuntimeEvidence, dict[str, Any]]:
    torch = prepared.torch
    with torch.inference_mode():
        output = prepared.model.forecast(
            prepared.inputs,
            horizon=request.prediction_length,
            decode_block_size=request.decode_block_size,
            has_missing_values=False,
        )
    if request.device == "cuda":
        torch.cuda.synchronize(prepared.device)
    expected = (9, 1, request.game_geometry.position_count, request.prediction_length)
    if tuple(int(value) for value in output.shape) != expected:
        raise RuntimeExecutionError(
            f"output shape mismatch: expected {expected}, got {tuple(output.shape)}"
        )
    if not bool(torch.isfinite(output).all().item()):
        raise RuntimeExecutionError("model output contains non-finite values")
    if not bool(((output[1:] - output[:-1]) >= -1e-6).all().item()):
        raise RuntimeExecutionError("native quantiles are not monotonic")
    output_device = str(output.device)
    cpu_fallback = request.device == "cuda" and (
        not prepared.model_device.startswith("cuda") or not output_device.startswith("cuda")
    )
    if cpu_fallback:
        raise RuntimeExecutionError("CUDA request fell back to CPU")
    peak_vram = (
        int(torch.cuda.max_memory_allocated(prepared.device)) if request.device == "cuda" else 0
    )
    native_output = output.detach().to("cpu", dtype=torch.float32).numpy()
    evidence = RuntimeEvidence(
        provider_pid=os.getpid(),
        requested_device=request.device,
        execution_device=output_device,
        model_device=prepared.model_device,
        output_device=output_device,
        peak_vram_bytes=peak_vram,
        external_gpu_pid_captured=False,
        cpu_fallback=cpu_fallback,
        runtime_scope="FULL_INFERENCE",
    )
    artifact_reference = {
        "snapshot": prepared.snapshot,
        "runtime": prepared.versions,
        "input_shape": list(prepared.target.shape),
        "output_shape": list(output.shape),
        "output_finite": True,
        "quantile_monotonicity": True,
        "vram_before_bytes": prepared.vram_before_bytes,
    }
    return native_output, evidence, artifact_reference
