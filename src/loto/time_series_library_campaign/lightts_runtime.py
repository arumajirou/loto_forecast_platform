from __future__ import annotations

import importlib
import os
import platform
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from .contracts import ProviderRequest, ProviderResponse, ProviderStatus, SourcePolicy
from .data import atomic_numpy, git_blob_sha, sha256_file
from .runtime import seed_everything, source_path

PINNED_LIGHTTS_GIT_BLOB = "a2051e44d864ec4ec5e72e59660b98c30c93a902"


def verify_pinned_lightts_source(source_root: Path) -> dict[str, Any]:
    path = source_root / "models/LightTS.py"
    if not path.is_file():
        raise ValueError("missing pinned source file: models/LightTS.py")
    actual = git_blob_sha(path)
    if actual != PINNED_LIGHTTS_GIT_BLOB:
        raise ValueError(
            "pinned source mismatch: models/LightTS.py: "
            f"expected {PINNED_LIGHTTS_GIT_BLOB}, got {actual}"
        )
    return {
        "status": "VERIFIED",
        "policy": "pinned",
        "model_name": "LightTS",
        "files": {
            "models/LightTS.py": {
                "expected_git_blob_sha": PINNED_LIGHTTS_GIT_BLOB,
                "actual_git_blob_sha": actual,
                "sha256": sha256_file(path),
            }
        },
    }


def source_evidence(request: ProviderRequest) -> dict[str, Any]:
    if request.source_policy == SourcePolicy.TEST_FIXTURE:
        return {
            "status": "TEST_FIXTURE",
            "policy": request.source_policy.value,
            "model_name": "LightTS",
        }
    return verify_pinned_lightts_source(request.source_root)


def load_lightts(source_root: Path) -> type[Any]:
    with source_path(source_root):
        model_class = getattr(importlib.import_module("models.LightTS"), "Model", None)
        if model_class is None:
            raise AttributeError("models.LightTS does not expose class Model")
        return model_class


def validate_lightts_config(config: dict[str, Any]) -> dict[str, Any]:
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["enc_in"])
    d_model = int(config["d_model"])
    dropout = float(config["dropout"])
    requested_chunk_size = int(config["lightts_chunk_size"])
    allow_padding = bool(config["lightts_allow_padding"])
    if seq_len < 4 or pred_len < 1 or channels < 1:
        raise ValueError("invalid LightTS sequence geometry")
    if d_model < 16:
        raise ValueError("LightTS requires d_model >= 16")
    if d_model % 4 != 0:
        raise ValueError("LightTS requires d_model divisible by 4")
    if not 0.0 <= dropout < 1.0:
        raise ValueError("LightTS dropout must be in [0, 1)")
    if requested_chunk_size < 1:
        raise ValueError("LightTS chunk size must be >= 1")
    chunk_size = min(pred_len, seq_len, requested_chunk_size)
    padded_seq_len = seq_len
    remainder = seq_len % chunk_size
    if remainder:
        padded_seq_len += chunk_size - remainder
    padding_length = padded_seq_len - seq_len
    if padding_length and not allow_padding:
        raise ValueError(
            "LightTS padding requires lightts_allow_padding=true: "
            f"padding_length={padding_length}"
        )
    return {
        "input_seq_len": seq_len,
        "pred_len": pred_len,
        "channels": channels,
        "d_model": d_model,
        "requested_chunk_size": requested_chunk_size,
        "chunk_size": chunk_size,
        "allow_padding": allow_padding,
        "padded_seq_len": padded_seq_len,
        "padding_length": padding_length,
        "num_chunks": padded_seq_len // chunk_size,
        "stage12_hidden_width": d_model // 4,
        "stage12_bottleneck_width": (d_model // 4) // 4,
        "stage3_input_width": d_model // 2,
        "stage3_bottleneck_width": (d_model // 2) // 4,
    }


def lightts_config(request: ProviderRequest) -> dict[str, Any]:
    config = {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "pred_len": request.pred_len,
        "enc_in": request.channels,
        "num_class": 1,
        "d_model": request.d_model,
        "dropout": request.dropout,
        "lightts_chunk_size": request.lightts_chunk_size,
        "lightts_allow_padding": request.lightts_allow_padding,
    }
    validate_lightts_config(config)
    return config


def build_lightts(source_root: Path, config: dict[str, Any]) -> Any:
    model_config = dict(config)
    chunk_size = int(model_config.pop("lightts_chunk_size"))
    model_config.pop("lightts_allow_padding")
    return load_lightts(source_root)(
        SimpleNamespace(**model_config),
        chunk_size=chunk_size,
    )


def runtime_evidence() -> dict[str, Any]:
    import torch

    return {
        "process_id": os.getpid(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "device": "cpu",
        "cuda_available": bool(torch.cuda.is_available()),
        "cpu_fallback": False,
    }


def verify_model_geometry(model: Any, geometry: dict[str, Any]) -> None:
    observed = {
        "chunk_size": int(model.chunk_size),
        "padded_seq_len": int(model.seq_len),
        "num_chunks": int(model.num_chunks),
    }
    expected = {
        "chunk_size": geometry["chunk_size"],
        "padded_seq_len": geometry["padded_seq_len"],
        "num_chunks": geometry["num_chunks"],
    }
    if observed != expected:
        raise ValueError(f"LightTS geometry mismatch: expected {expected}, got {observed}")


def fit_save(request: ProviderRequest) -> ProviderResponse:
    import torch

    identity = source_evidence(request)
    seed_everything(request.seed)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    config = lightts_config(request)
    geometry = validate_lightts_config(config)
    model = build_lightts(request.source_root, config).to("cpu")
    verify_model_geometry(model, geometry)
    x = torch.linspace(
        0.0,
        1.0,
        steps=2 * request.seq_len * request.channels,
        dtype=torch.float32,
    ).reshape(2, request.seq_len, request.channels)
    target = x[:, -1:, :].repeat(1, request.pred_len, 1)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    model.train()
    for _ in range(request.train_steps):
        optimizer.zero_grad(set_to_none=True)
        prediction = model(x, None, None, None)
        torch.mean((prediction - target) ** 2).backward()
        optimizer.step()
    model.eval()
    with torch.no_grad():
        prediction = model(x, None, None, None).cpu().numpy()
    expected = (2, request.pred_len, request.channels)
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid prediction shape or values: {prediction.shape}")
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    if parameter_devices != ["cpu"]:
        raise ValueError(f"unexpected parameter devices: {parameter_devices}")
    state = model.state_dict()
    if not state or not all(torch.isfinite(value).all().item() for value in state.values()):
        raise ValueError("state_dict is missing or non-finite")
    checkpoint = request.output_dir / "checkpoint.pt"
    with tempfile.NamedTemporaryFile(mode="wb", dir=request.output_dir, delete=False) as handle:
        temporary = Path(handle.name)
    torch.save(
        {
            "state_dict": state,
            "config": config,
            "geometry": geometry,
            "model_name": "LightTS",
        },
        temporary,
    )
    os.replace(temporary, checkpoint)
    input_path = request.output_dir / "input.npz"
    before_path = request.output_dir / "prediction_before.npy"
    atomic_numpy(input_path, lambda handle: np.savez(handle, x=x.cpu().numpy()))
    atomic_numpy(before_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name="LightTS",
        artifacts={
            "checkpoint": str(checkpoint),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            **runtime_evidence(),
            "model_class": "models.LightTS.Model",
            "effective_config": config,
            "chunk_geometry": geometry,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "finite_state_dict": True,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "parameter_devices": parameter_devices,
            "input_device": str(x.device),
            "output_device": "cpu",
            "train_steps": request.train_steps,
            "source_identity": identity,
            "checkpoint_sha256": sha256_file(checkpoint),
            "input_sha256": sha256_file(input_path),
            "prediction_sha256": sha256_file(before_path),
        },
    )


def load_predict(request: ProviderRequest) -> ProviderResponse:
    import torch

    assert request.checkpoint_path is not None
    assert request.input_path is not None
    identity = source_evidence(request)
    seed_everything(request.seed)
    checkpoint = torch.load(request.checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("model_name") != "LightTS":
        raise ValueError("checkpoint model mismatch: expected LightTS")
    config = checkpoint["config"]
    geometry = validate_lightts_config(config)
    if checkpoint.get("geometry") != geometry:
        raise ValueError("checkpoint LightTS geometry mismatch")
    model = build_lightts(request.source_root, config)
    verify_model_geometry(model, geometry)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    with np.load(request.input_path) as payload:
        x = torch.from_numpy(payload["x"]).to(dtype=torch.float32)
    expected_input = (2, geometry["input_seq_len"], geometry["channels"])
    if tuple(x.shape) != expected_input:
        raise ValueError(
            "invalid LightTS input shape: "
            f"expected {expected_input}, got {tuple(x.shape)}"
        )
    with torch.no_grad():
        prediction = model(x, None, None, None).cpu().numpy()
    expected = (2, geometry["pred_len"], geometry["channels"])
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid reloaded prediction: {prediction.shape}")
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    if parameter_devices != ["cpu"]:
        raise ValueError(f"unexpected parameter devices: {parameter_devices}")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    after_path = request.output_dir / "prediction_after.npy"
    atomic_numpy(after_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name="LightTS",
        artifacts={"prediction_after": str(after_path)},
        evidence={
            **runtime_evidence(),
            "model_class": "models.LightTS.Model",
            "chunk_geometry": geometry,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "strict_state_load": True,
            "parameter_devices": parameter_devices,
            "input_device": str(x.device),
            "output_device": "cpu",
            "source_identity": identity,
            "prediction_sha256": sha256_file(after_path),
        },
    )
