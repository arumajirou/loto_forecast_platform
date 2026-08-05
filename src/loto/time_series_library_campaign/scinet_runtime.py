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

PINNED_SCINET_GIT_BLOB = "740d0f7d88e8a94aa7fe12c745f0876af7b0fc08"
SCINET_TREE_LEVEL = 3
SCINET_KERNEL_SIZE = 5
SCINET_BLOCKS_PER_TREE = 15
SCINET_CAUSAL_BLOCKS_PER_SCI_BLOCK = 4


def verify_pinned_scinet_source(source_root: Path) -> dict[str, Any]:
    path = source_root / "models/SCINet.py"
    if not path.is_file():
        raise ValueError("missing pinned source file: models/SCINet.py")
    actual = git_blob_sha(path)
    if actual != PINNED_SCINET_GIT_BLOB:
        raise ValueError(
            "pinned source mismatch: models/SCINet.py: "
            f"expected {PINNED_SCINET_GIT_BLOB}, got {actual}"
        )
    return {
        "status": "VERIFIED",
        "policy": "pinned",
        "model_name": "SCINet",
        "files": {
            "models/SCINet.py": {
                "expected_git_blob_sha": PINNED_SCINET_GIT_BLOB,
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
            "model_name": "SCINet",
        }
    return verify_pinned_scinet_source(request.source_root)


def load_scinet(source_root: Path) -> type[Any]:
    with source_path(source_root):
        model_class = getattr(importlib.import_module("models.SCINet"), "Model", None)
        if model_class is None:
            raise AttributeError("models.SCINet does not expose class Model")
        return model_class


def expected_parameter_count(seq_len: int, pred_len: int, channels: int, stacks: int) -> int:
    if stacks == 1:
        return 600 * channels**2 + 120 * channels + seq_len * (seq_len + pred_len)
    return (
        1200 * channels**2
        + 240 * channels
        + seq_len * pred_len
        + (seq_len + pred_len) ** 2
    )


def validate_scinet_config(config: dict[str, Any]) -> dict[str, Any]:
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["enc_in"])
    stacks = int(config["d_layers"])
    dropout = float(config["dropout"])
    if seq_len < 8:
        raise ValueError("SCINet requires seq_len >= 8 for tree level 3")
    if pred_len < 1 or channels < 1:
        raise ValueError("invalid SCINet forecast geometry")
    if stacks not in {1, 2}:
        raise ValueError("SCINet stacks must be 1 or 2")
    if dropout != 0.0:
        raise ValueError("SCINet requires dropout=0.0 because upstream ignores it")
    pe_hidden_size = channels if channels % 2 == 0 else channels + 1
    return {
        "seq_len": seq_len,
        "pred_len": pred_len,
        "channels": channels,
        "stacks": stacks,
        "tree_level": SCINET_TREE_LEVEL,
        "tree_depth": SCINET_TREE_LEVEL + 1,
        "sci_blocks_per_tree": SCINET_BLOCKS_PER_TREE,
        "causal_conv_blocks_per_sci_block": SCINET_CAUSAL_BLOCKS_PER_SCI_BLOCK,
        "kernel_size": SCINET_KERNEL_SIZE,
        "requested_dropout": dropout,
        "effective_dropout": 0.0,
        "pe_hidden_size": pe_hidden_size,
        "inv_timescales_length": pe_hidden_size // 2,
        "raw_output_length": 2 * seq_len + pred_len,
        "forecast_slice_start": 2 * seq_len,
        "expected_parameter_count": expected_parameter_count(
            seq_len, pred_len, channels, stacks
        ),
    }


def scinet_config(request: ProviderRequest) -> dict[str, Any]:
    config = {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "label_len": 0,
        "pred_len": request.pred_len,
        "d_layers": request.scinet_stacks,
        "enc_in": request.channels,
        "dropout": request.dropout,
    }
    validate_scinet_config(config)
    return config


def build_scinet(source_root: Path, config: dict[str, Any]) -> Any:
    return load_scinet(source_root)(SimpleNamespace(**config))


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


def verify_model_geometry(
    model: Any,
    geometry: dict[str, Any],
    *,
    strict_structure: bool,
) -> None:
    observed = {
        "seq_len": int(model.seq_len),
        "pred_len": int(model.pred_len),
        "stacks": int(model.num_stacks),
        "pe_hidden_size": int(model.pe_hidden_size),
        "inv_timescales_length": int(model.inv_timescales.numel()),
    }
    expected = {
        "seq_len": geometry["seq_len"],
        "pred_len": geometry["pred_len"],
        "stacks": geometry["stacks"],
        "pe_hidden_size": geometry["pe_hidden_size"],
        "inv_timescales_length": geometry["inv_timescales_length"],
    }
    if observed != expected:
        raise ValueError(f"SCINet geometry mismatch: expected {expected}, got {observed}")
    if not strict_structure:
        return
    modules = list(model.modules())
    sci_blocks = sum(module.__class__.__name__ == "SCIBlock" for module in modules)
    causal_blocks = sum(
        module.__class__.__name__ == "CausalConvBlock" for module in modules
    )
    expected_sci_blocks = geometry["sci_blocks_per_tree"] * geometry["stacks"]
    expected_causal_blocks = (
        expected_sci_blocks * geometry["causal_conv_blocks_per_sci_block"]
    )
    if sci_blocks != expected_sci_blocks or causal_blocks != expected_causal_blocks:
        raise ValueError(
            "SCINet module-count mismatch: "
            f"SCIBlock={sci_blocks}/{expected_sci_blocks}, "
            f"CausalConvBlock={causal_blocks}/{expected_causal_blocks}"
        )
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count != geometry["expected_parameter_count"]:
        raise ValueError(
            "SCINet parameter count mismatch: "
            f"expected {geometry['expected_parameter_count']}, got {parameter_count}"
        )


def split_forecast(raw: Any, geometry: dict[str, Any]) -> Any:
    expected_raw = (
        2,
        geometry["raw_output_length"],
        geometry["channels"],
    )
    if tuple(raw.shape) != expected_raw:
        raise ValueError(
            f"invalid SCINet raw output shape: expected {expected_raw}, got {tuple(raw.shape)}"
        )
    prefix = raw[:, : geometry["seq_len"], :]
    if not bool((prefix == 0).all().item()):
        raise ValueError("SCINet raw output prefix is not zero-filled")
    return raw[:, -geometry["pred_len"] :, :]


def fit_save(request: ProviderRequest) -> ProviderResponse:
    import torch

    identity = source_evidence(request)
    seed_everything(request.seed)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    config = scinet_config(request)
    geometry = validate_scinet_config(config)
    model = build_scinet(request.source_root, config).to("cpu")
    verify_model_geometry(
        model,
        geometry,
        strict_structure=request.source_policy == SourcePolicy.PINNED,
    )
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
        raw = model(x, None, None, None)
        prediction = split_forecast(raw, geometry)
        loss = torch.mean((prediction - target) ** 2)
        if not torch.isfinite(loss).item():
            raise ValueError("SCINet training loss is non-finite")
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    model.eval()
    with torch.no_grad():
        raw_tensor = model(x, None, None, None)
        prediction_tensor = split_forecast(raw_tensor, geometry)
        prediction = prediction_tensor.cpu().numpy()
    expected = (2, request.pred_len, request.channels)
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid SCINet prediction: {prediction.shape}")
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
            "model_name": "SCINet",
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
        model_name="SCINet",
        artifacts={
            "checkpoint": str(checkpoint),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            **runtime_evidence(),
            "model_class": "models.SCINet.Model",
            "effective_config": config,
            "tree_geometry": geometry,
            "raw_output_shape": list(raw_tensor.shape),
            "prediction_shape": list(prediction.shape),
            "zero_prefix_verified": True,
            "finite_prediction": True,
            "finite_state_dict": True,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
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
    if checkpoint.get("model_name") != "SCINet":
        raise ValueError("checkpoint model mismatch: expected SCINet")
    config = checkpoint["config"]
    geometry = validate_scinet_config(config)
    if checkpoint.get("geometry") != geometry:
        raise ValueError("checkpoint SCINet geometry mismatch")
    model = build_scinet(request.source_root, config).to("cpu")
    verify_model_geometry(
        model,
        geometry,
        strict_structure=request.source_policy == SourcePolicy.PINNED,
    )
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    with np.load(request.input_path) as payload:
        x = torch.from_numpy(payload["x"]).to(dtype=torch.float32)
    expected_input = (2, geometry["seq_len"], geometry["channels"])
    if tuple(x.shape) != expected_input:
        raise ValueError(
            "invalid SCINet input shape: "
            f"expected {expected_input}, got {tuple(x.shape)}"
        )
    with torch.no_grad():
        raw_tensor = model(x, None, None, None)
        prediction_tensor = split_forecast(raw_tensor, geometry)
        prediction = prediction_tensor.cpu().numpy()
    expected = (2, geometry["pred_len"], geometry["channels"])
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid reloaded SCINet prediction: {prediction.shape}")
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    if parameter_devices != ["cpu"]:
        raise ValueError(f"unexpected parameter devices: {parameter_devices}")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    after_path = request.output_dir / "prediction_after.npy"
    atomic_numpy(after_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name="SCINet",
        artifacts={"prediction_after": str(after_path)},
        evidence={
            **runtime_evidence(),
            "model_class": "models.SCINet.Model",
            "tree_geometry": geometry,
            "raw_output_shape": list(raw_tensor.shape),
            "prediction_shape": list(prediction.shape),
            "zero_prefix_verified": True,
            "finite_prediction": True,
            "strict_state_load": True,
            "parameter_devices": parameter_devices,
            "input_device": str(x.device),
            "output_device": str(prediction_tensor.device),
            "source_identity": identity,
            "prediction_sha256": sha256_file(after_path),
        },
    )
