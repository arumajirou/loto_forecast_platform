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

PINNED_TIDE_GIT_BLOB = "0fbb98ea159ec5aa5d7afed83eddaf4c2476eaf1"
TIDE_FEATURE_ENCODE_DIM = 2
TIDE_FREQ_DIMENSIONS = {"h": 4, "t": 5, "s": 6, "m": 1, "a": 1, "w": 2, "d": 3, "b": 3}


def verify_pinned_tide_source(source_root: Path) -> dict[str, Any]:
    path = source_root / "models" / "TiDE.py"
    if not path.is_file():
        raise ValueError("missing models/TiDE.py")
    actual = git_blob_sha(path)
    if actual != PINNED_TIDE_GIT_BLOB:
        raise ValueError(
            f"pinned source mismatch: models/TiDE.py: expected {PINNED_TIDE_GIT_BLOB}, got {actual}"
        )
    return {
        "status": "VERIFIED",
        "policy": "pinned",
        "model_name": "TiDE",
        "files": {
            "models/TiDE.py": {
                "expected_git_blob_sha": PINNED_TIDE_GIT_BLOB,
                "actual_git_blob_sha": actual,
                "sha256": sha256_file(path),
            }
        },
    }


def source_evidence(request: ProviderRequest) -> dict[str, Any]:
    if request.source_policy == SourcePolicy.TEST_FIXTURE:
        return {"status": "TEST_FIXTURE", "policy": "test_fixture", "model_name": "TiDE"}
    return verify_pinned_tide_source(request.source_root)


def load_tide(source_root: Path) -> type[Any]:
    with source_path(source_root):
        model_class = getattr(importlib.import_module("models.TiDE"), "Model", None)
        if model_class is None:
            raise AttributeError("models.TiDE does not expose class Model")
        return model_class


def tide_config(request: ProviderRequest) -> dict[str, Any]:
    return {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "label_len": 0,
        "pred_len": request.pred_len,
        "d_model": request.d_model,
        "e_layers": request.e_layers,
        "d_layers": request.tide_d_layers,
        "freq": request.tide_freq,
        "c_out": request.channels,
        "d_ff": request.tide_d_ff,
        "dropout": request.dropout,
    }


def resblock_parameter_count(input_dim: int, hidden_dim: int, output_dim: int) -> int:
    return (
        input_dim * hidden_dim
        + hidden_dim
        + hidden_dim * output_dim
        + input_dim * output_dim
        + 4 * output_dim
    )


def expected_parameter_count(config: dict[str, Any]) -> int:
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["c_out"])
    d_model = int(config["d_model"])
    d_ff = int(config["d_ff"])
    feature_dim = TIDE_FREQ_DIMENSIONS[str(config["freq"])]
    flatten_dim = seq_len + (seq_len + pred_len) * TIDE_FEATURE_ENCODE_DIM
    return (
        resblock_parameter_count(feature_dim, d_model, TIDE_FEATURE_ENCODE_DIM)
        + resblock_parameter_count(flatten_dim, d_model, d_model)
        + resblock_parameter_count(d_model, d_model, channels * pred_len)
        + resblock_parameter_count(channels + TIDE_FEATURE_ENCODE_DIM, d_ff, 1)
        + seq_len * pred_len
        + pred_len
    )


def validate_tide_config(config: dict[str, Any]) -> dict[str, Any]:
    if int(config["e_layers"]) != 1 or int(config["d_layers"]) != 1:
        raise ValueError("TiDE certified lane requires one encoder and one decoder layer")
    if float(config["dropout"]) != 0.0:
        raise ValueError("TiDE certified lane requires dropout=0.0")
    freq = str(config["freq"])
    if freq not in TIDE_FREQ_DIMENSIONS:
        raise ValueError(f"unsupported TiDE frequency: {freq}")
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["c_out"])
    d_model = int(config["d_model"])
    d_ff = int(config["d_ff"])
    if min(seq_len, pred_len, channels, d_model, d_ff) < 1:
        raise ValueError("invalid TiDE positive geometry")
    feature_dim = TIDE_FREQ_DIMENSIONS[freq]
    flatten_dim = seq_len + (seq_len + pred_len) * TIDE_FEATURE_ENCODE_DIM
    return {
        "seq_len": seq_len,
        "pred_len": pred_len,
        "channels": channels,
        "d_model": d_model,
        "d_ff": d_ff,
        "e_layers": 1,
        "d_layers": 1,
        "freq": freq,
        "feature_dim": feature_dim,
        "feature_encode_dim": TIDE_FEATURE_ENCODE_DIM,
        "flatten_dim": flatten_dim,
        "time_marks": "internal_zero_features_only",
        "shared_layer_aliasing": False,
        "expected_parameter_count": expected_parameter_count(config),
    }


def build_tide(source_root: Path, config: dict[str, Any]) -> Any:
    return load_tide(source_root)(SimpleNamespace(**config))


def verify_model_geometry(model: Any, geometry: dict[str, Any]) -> None:
    observed = {
        "seq_len": int(model.seq_len),
        "pred_len": int(model.pred_len),
        "channels": int(model.decode_dim),
        "d_model": int(model.hidden_dim),
        "d_ff": int(model.temporalDecoderHidden),
        "e_layers": int(model.encoder_num),
        "d_layers": int(model.decoder_num),
        "freq": str(model.freq),
        "feature_dim": int(model.feature_dim),
        "feature_encode_dim": int(model.feature_encode_dim),
    }
    expected = {key: geometry[key] for key in observed}
    if observed != expected:
        raise ValueError(f"TiDE geometry mismatch: expected {expected}, got {observed}")
    if len(model.encoders) != 1 or len(model.decoders) != 1:
        raise ValueError("TiDE certified lane requires exactly one encoder and decoder module")
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count != geometry["expected_parameter_count"]:
        raise ValueError(
            "TiDE parameter count mismatch: "
            f"expected {geometry['expected_parameter_count']}, got {parameter_count}"
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


def fit_save(request: ProviderRequest) -> ProviderResponse:
    import torch

    identity = source_evidence(request)
    seed_everything(request.seed)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    config = tide_config(request)
    geometry = validate_tide_config(config)
    model = build_tide(request.source_root, config).to("cpu")
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
        prediction_tensor = model(x, None, None, None)
        loss = torch.mean((prediction_tensor - target) ** 2)
        if not torch.isfinite(loss).item():
            raise ValueError("TiDE training loss is non-finite")
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    model.eval()
    with torch.no_grad():
        prediction_tensor = model(x, None, None, None)
        prediction = prediction_tensor.cpu().numpy()
    expected = (2, request.pred_len, request.channels)
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid TiDE prediction: {prediction.shape}")
    state = model.state_dict()
    if not state or not all(torch.isfinite(value).all().item() for value in state.values()):
        raise ValueError("state_dict is missing or non-finite")
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    if parameter_devices != ["cpu"]:
        raise ValueError(f"unexpected parameter devices: {parameter_devices}")
    checkpoint_path = request.output_dir / "checkpoint.pt"
    with tempfile.NamedTemporaryFile(mode="wb", dir=request.output_dir, delete=False) as handle:
        temporary = Path(handle.name)
    torch.save(
        {"state_dict": state, "config": config, "geometry": geometry, "model_name": "TiDE"},
        temporary,
    )
    os.replace(temporary, checkpoint_path)
    input_path = request.output_dir / "input.npz"
    before_path = request.output_dir / "prediction_before.npy"
    atomic_numpy(input_path, lambda handle: np.savez(handle, x=x.cpu().numpy()))
    atomic_numpy(before_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name="TiDE",
        artifacts={
            "checkpoint": str(checkpoint_path),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            **runtime_evidence(),
            "model_class": "models.TiDE.Model",
            "effective_config": config,
            "geometry": geometry,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "finite_state_dict": True,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "parameter_devices": parameter_devices,
            "input_device": str(x.device),
            "output_device": str(prediction_tensor.device),
            "train_steps": request.train_steps,
            "losses": losses,
            "source_identity": identity,
            "checkpoint_sha256": sha256_file(checkpoint_path),
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
    if checkpoint.get("model_name") != "TiDE":
        raise ValueError("checkpoint model mismatch: expected TiDE")
    config = checkpoint["config"]
    geometry = validate_tide_config(config)
    if checkpoint.get("geometry") != geometry:
        raise ValueError("checkpoint TiDE geometry mismatch")
    model = build_tide(request.source_root, config).to("cpu")
    verify_model_geometry(model, geometry)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    with np.load(request.input_path) as payload:
        x = torch.from_numpy(payload["x"]).to(dtype=torch.float32)
    expected_input = (2, geometry["seq_len"], geometry["channels"])
    if tuple(x.shape) != expected_input:
        raise ValueError(
            f"invalid TiDE input shape: expected {expected_input}, got {tuple(x.shape)}"
        )
    with torch.no_grad():
        prediction_tensor = model(x, None, None, None)
        prediction = prediction_tensor.cpu().numpy()
    expected = (2, geometry["pred_len"], geometry["channels"])
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid reloaded TiDE prediction: {prediction.shape}")
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    if parameter_devices != ["cpu"]:
        raise ValueError(f"unexpected parameter devices: {parameter_devices}")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    after_path = request.output_dir / "prediction_after.npy"
    atomic_numpy(after_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name="TiDE",
        artifacts={"prediction_after": str(after_path)},
        evidence={
            **runtime_evidence(),
            "model_class": "models.TiDE.Model",
            "geometry": geometry,
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
