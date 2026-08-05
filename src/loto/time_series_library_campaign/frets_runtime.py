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

PINNED_FRETS_GIT_BLOB = "ca4e0b648db42a1846b7a0a9a661a39177f47005"
FRETS_EMBED_SIZE = 128
FRETS_HIDDEN_SIZE = 256
FRETS_SPARSITY_THRESHOLD = 0.01
FRETS_SCALE = 0.02


def verify_pinned_frets_source(source_root: Path) -> dict[str, Any]:
    path = source_root / "models/FreTS.py"
    if not path.is_file():
        raise ValueError("missing pinned source file: models/FreTS.py")
    actual = git_blob_sha(path)
    if actual != PINNED_FRETS_GIT_BLOB:
        raise ValueError(
            "pinned source mismatch: models/FreTS.py: "
            f"expected {PINNED_FRETS_GIT_BLOB}, got {actual}"
        )
    return {
        "status": "VERIFIED",
        "policy": "pinned",
        "model_name": "FreTS",
        "files": {
            "models/FreTS.py": {
                "expected_git_blob_sha": PINNED_FRETS_GIT_BLOB,
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
            "model_name": "FreTS",
        }
    return verify_pinned_frets_source(request.source_root)


def load_frets(source_root: Path) -> type[Any]:
    with source_path(source_root):
        model_class = getattr(importlib.import_module("models.FreTS"), "Model", None)
        if model_class is None:
            raise AttributeError("models.FreTS does not expose class Model")
        return model_class


def expected_parameter_count(seq_len: int, pred_len: int) -> int:
    return 66_432 + 32_768 * seq_len + 257 * pred_len


def validate_frets_config(config: dict[str, Any]) -> dict[str, Any]:
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["enc_in"])
    channel_independence = str(config["channel_independence"])
    if seq_len < 4 or pred_len < 1 or channels < 1:
        raise ValueError("invalid FreTS sequence geometry")
    if channel_independence not in {"0", "1"}:
        raise ValueError("FreTS channel_independence must be '0' or '1'")
    return {
        "seq_len": seq_len,
        "pred_len": pred_len,
        "channels": channels,
        "channel_independence": channel_independence,
        "channel_frequency_mixing": channel_independence == "0",
        "embed_size": FRETS_EMBED_SIZE,
        "hidden_size": FRETS_HIDDEN_SIZE,
        "sparsity_threshold": FRETS_SPARSITY_THRESHOLD,
        "scale": FRETS_SCALE,
        "temporal_fft_bins": seq_len // 2 + 1,
        "channel_fft_bins": channels // 2 + 1,
        "expected_parameter_count": expected_parameter_count(seq_len, pred_len),
    }


def frets_config(request: ProviderRequest) -> dict[str, Any]:
    config = {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "pred_len": request.pred_len,
        "enc_in": request.channels,
        "channel_independence": request.frets_channel_independence,
    }
    validate_frets_config(config)
    return config


def build_frets(source_root: Path, config: dict[str, Any]) -> Any:
    return load_frets(source_root)(SimpleNamespace(**config))


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
        "seq_len": int(model.seq_len),
        "pred_len": int(model.pred_len),
        "channels": int(model.feature_size),
        "channel_independence": str(model.channel_independence),
        "embed_size": int(model.embed_size),
        "hidden_size": int(model.hidden_size),
        "sparsity_threshold": float(model.sparsity_threshold),
        "scale": float(model.scale),
        "embedding_shape": list(model.embeddings.shape),
    }
    expected = {
        "seq_len": geometry["seq_len"],
        "pred_len": geometry["pred_len"],
        "channels": geometry["channels"],
        "channel_independence": geometry["channel_independence"],
        "embed_size": geometry["embed_size"],
        "hidden_size": geometry["hidden_size"],
        "sparsity_threshold": geometry["sparsity_threshold"],
        "scale": geometry["scale"],
        "embedding_shape": [1, geometry["embed_size"]],
    }
    if observed != expected:
        raise ValueError(f"FreTS geometry mismatch: expected {expected}, got {observed}")
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count != geometry["expected_parameter_count"]:
        raise ValueError(
            "FreTS parameter count mismatch: "
            f"expected {geometry['expected_parameter_count']}, got {parameter_count}"
        )


def fit_save(request: ProviderRequest) -> ProviderResponse:
    import torch

    identity = source_evidence(request)
    seed_everything(request.seed)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    config = frets_config(request)
    geometry = validate_frets_config(config)
    model = build_frets(request.source_root, config).to("cpu")
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
    losses: list[float] = []
    for _ in range(request.train_steps):
        optimizer.zero_grad(set_to_none=True)
        prediction = model(x, None, None, None)
        loss = torch.mean((prediction - target) ** 2)
        if not torch.isfinite(loss).item():
            raise ValueError("FreTS training loss is non-finite")
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    model.eval()
    with torch.no_grad():
        prediction_tensor = model(x, None, None, None)
        prediction = prediction_tensor.cpu().numpy()
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
            "model_name": "FreTS",
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
        model_name="FreTS",
        artifacts={
            "checkpoint": str(checkpoint),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            **runtime_evidence(),
            "model_class": "models.FreTS.Model",
            "effective_config": config,
            "frequency_geometry": geometry,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "finite_state_dict": True,
            "parameter_count": geometry["expected_parameter_count"],
            "parameter_devices": parameter_devices,
            "input_device": str(x.device),
            "output_device": str(prediction_tensor.device),
            "train_steps": request.train_steps,
            "losses": losses,
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
    if checkpoint.get("model_name") != "FreTS":
        raise ValueError("checkpoint model mismatch: expected FreTS")
    config = checkpoint["config"]
    geometry = validate_frets_config(config)
    if checkpoint.get("geometry") != geometry:
        raise ValueError("checkpoint FreTS geometry mismatch")
    model = build_frets(request.source_root, config).to("cpu")
    verify_model_geometry(model, geometry)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    with np.load(request.input_path) as payload:
        x = torch.from_numpy(payload["x"]).to(dtype=torch.float32)
    expected_input = (2, geometry["seq_len"], geometry["channels"])
    if tuple(x.shape) != expected_input:
        raise ValueError(
            "invalid FreTS input shape: "
            f"expected {expected_input}, got {tuple(x.shape)}"
        )
    with torch.no_grad():
        prediction_tensor = model(x, None, None, None)
        prediction = prediction_tensor.cpu().numpy()
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
        model_name="FreTS",
        artifacts={"prediction_after": str(after_path)},
        evidence={
            **runtime_evidence(),
            "model_class": "models.FreTS.Model",
            "frequency_geometry": geometry,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "strict_state_load": True,
            "parameter_devices": parameter_devices,
            "input_device": str(x.device),
            "output_device": str(prediction_tensor.device),
            "source_identity": identity,
            "prediction_sha256": sha256_file(after_path),
        },
    )
