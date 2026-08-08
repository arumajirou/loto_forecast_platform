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

PINNED_SEGRNN_GIT_BLOBS = {
    "models/SegRNN.py": "afff1bc07dd14d227bbecdd36941d57f8aa8f63e",
    "layers/Autoformer_EncDec.py": "6fce4bcd6b3d3eb00e9bcf5931ed2ee301554f4a",
}


def verify_pinned_segrnn_source(source_root: Path) -> dict[str, Any]:
    files: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    for relative_path, expected in PINNED_SEGRNN_GIT_BLOBS.items():
        path = source_root / relative_path
        if not path.is_file():
            errors.append(f"missing pinned source file: {relative_path}")
            continue
        actual = git_blob_sha(path)
        files[relative_path] = {
            "expected_git_blob_sha": expected,
            "actual_git_blob_sha": actual,
            "sha256": sha256_file(path),
        }
        if actual != expected:
            errors.append(
                f"pinned source mismatch: {relative_path}: expected {expected}, got {actual}"
            )
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "VERIFIED",
        "policy": "pinned",
        "model_name": "SegRNN",
        "files": files,
    }


def source_evidence(request: ProviderRequest) -> dict[str, Any]:
    if request.source_policy == SourcePolicy.TEST_FIXTURE:
        return {
            "status": "TEST_FIXTURE",
            "policy": request.source_policy.value,
            "model_name": "SegRNN",
        }
    return verify_pinned_segrnn_source(request.source_root)


def load_segrnn(source_root: Path) -> type[Any]:
    with source_path(source_root):
        model_class = getattr(importlib.import_module("models.SegRNN"), "Model", None)
        if model_class is None:
            raise AttributeError("models.SegRNN does not expose class Model")
        return model_class


def validate_segrnn_config(config: dict[str, Any]) -> dict[str, Any]:
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["enc_in"])
    d_model = int(config["d_model"])
    dropout = float(config["dropout"])
    seg_len = int(config["seg_len"])
    if seq_len < 4 or pred_len < 1 or channels < 1:
        raise ValueError("invalid SegRNN sequence geometry")
    if d_model < 2 or d_model % 2 != 0:
        raise ValueError("SegRNN requires even d_model >= 2")
    if not 0.0 <= dropout < 1.0:
        raise ValueError("SegRNN dropout must be in [0, 1)")
    if seg_len < 1:
        raise ValueError("SegRNN seg_len must be >= 1")
    if seq_len % seg_len != 0:
        raise ValueError("SegRNN requires seq_len divisible by seg_len")
    if pred_len % seg_len != 0:
        raise ValueError("SegRNN requires pred_len divisible by seg_len")
    return {
        "seq_len": seq_len,
        "pred_len": pred_len,
        "channels": channels,
        "d_model": d_model,
        "dropout": dropout,
        "seg_len": seg_len,
        "seg_num_x": seq_len // seg_len,
        "seg_num_y": pred_len // seg_len,
        "half_width": d_model // 2,
        "decoder_tokens_per_batch": channels * (pred_len // seg_len),
    }


def segrnn_config(request: ProviderRequest) -> dict[str, Any]:
    config = {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "pred_len": request.pred_len,
        "enc_in": request.channels,
        "d_model": request.d_model,
        "dropout": request.dropout,
        "seg_len": request.segrnn_seg_len,
        "num_class": 1,
    }
    validate_segrnn_config(config)
    return config


def build_segrnn(source_root: Path, config: dict[str, Any]) -> Any:
    return load_segrnn(source_root)(SimpleNamespace(**config))


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
        "channels": int(model.enc_in),
        "d_model": int(model.d_model),
        "seg_len": int(model.seg_len),
        "seg_num_x": int(model.seg_num_x),
        "seg_num_y": int(model.seg_num_y),
        "pos_emb_shape": list(model.pos_emb.shape),
        "channel_emb_shape": list(model.channel_emb.shape),
    }
    expected = {
        "seq_len": geometry["seq_len"],
        "pred_len": geometry["pred_len"],
        "channels": geometry["channels"],
        "d_model": geometry["d_model"],
        "seg_len": geometry["seg_len"],
        "seg_num_x": geometry["seg_num_x"],
        "seg_num_y": geometry["seg_num_y"],
        "pos_emb_shape": [geometry["seg_num_y"], geometry["half_width"]],
        "channel_emb_shape": [geometry["channels"], geometry["half_width"]],
    }
    if observed != expected:
        raise ValueError(f"SegRNN geometry mismatch: expected {expected}, got {observed}")


def fit_save(request: ProviderRequest) -> ProviderResponse:
    import torch

    identity = source_evidence(request)
    seed_everything(request.seed)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    config = segrnn_config(request)
    geometry = validate_segrnn_config(config)
    model = build_segrnn(request.source_root, config).to("cpu")
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
            "model_name": "SegRNN",
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
        model_name="SegRNN",
        artifacts={
            "checkpoint": str(checkpoint),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            **runtime_evidence(),
            "model_class": "models.SegRNN.Model",
            "effective_config": config,
            "segment_geometry": geometry,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "finite_state_dict": True,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "parameter_devices": parameter_devices,
            "input_device": str(x.device),
            "output_device": str(prediction_tensor.device),
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
    if checkpoint.get("model_name") != "SegRNN":
        raise ValueError("checkpoint model mismatch: expected SegRNN")
    config = checkpoint["config"]
    geometry = validate_segrnn_config(config)
    if checkpoint.get("geometry") != geometry:
        raise ValueError("checkpoint SegRNN geometry mismatch")
    model = build_segrnn(request.source_root, config).to("cpu")
    verify_model_geometry(model, geometry)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    with np.load(request.input_path) as payload:
        x = torch.from_numpy(payload["x"]).to(dtype=torch.float32)
    expected_input = (2, geometry["seq_len"], geometry["channels"])
    if tuple(x.shape) != expected_input:
        raise ValueError(
            f"invalid SegRNN input shape: expected {expected_input}, got {tuple(x.shape)}"
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
        model_name="SegRNN",
        artifacts={"prediction_after": str(after_path)},
        evidence={
            **runtime_evidence(),
            "model_class": "models.SegRNN.Model",
            "segment_geometry": geometry,
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
