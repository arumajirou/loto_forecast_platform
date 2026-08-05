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

PINNED_TIMEFILTER_GIT_BLOBS = {
    "models/TimeFilter.py": "ff952b4a7741ad2772fde3e41b0d97bc2bbe7e19",
    "layers/TimeFilter_layers.py": "437c3bfd135c2d2b907c7332311ac553c8a2d523",
    "layers/StandardNorm.py": "990d0fdc17751b724354e70b89fd6d3ff0f4dd29",
    "layers/Embed.py": "977e25568d37b9dd0efd442dcc5b33eab9843d71",
}
TIMEFILTER_POSITIONAL_LIMIT = 10000
TIMEFILTER_EXPERT_COUNT = 3


def verify_pinned_timefilter_source(source_root: Path) -> dict[str, Any]:
    files: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    for relative, expected in PINNED_TIMEFILTER_GIT_BLOBS.items():
        path = source_root / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
            continue
        actual = git_blob_sha(path)
        if actual != expected:
            errors.append(f"{relative}: expected {expected}, got {actual}")
        files[relative] = {
            "expected_git_blob_sha": expected,
            "actual_git_blob_sha": actual,
            "sha256": sha256_file(path),
        }
    if errors:
        raise ValueError("pinned source mismatch: " + "; ".join(errors))
    return {
        "status": "VERIFIED",
        "policy": "pinned",
        "model_name": "TimeFilter",
        "files": files,
    }


def source_evidence(request: ProviderRequest) -> dict[str, Any]:
    if request.source_policy == SourcePolicy.TEST_FIXTURE:
        return {
            "status": "TEST_FIXTURE",
            "policy": request.source_policy.value,
            "model_name": "TimeFilter",
        }
    return verify_pinned_timefilter_source(request.source_root)


def load_timefilter(source_root: Path) -> type[Any]:
    with source_path(source_root):
        model_class = getattr(importlib.import_module("models.TimeFilter"), "Model", None)
        if model_class is None:
            raise AttributeError("models.TimeFilter does not expose class Model")
        return model_class


def expected_parameter_count(config: dict[str, Any]) -> int:
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["c_out"])
    d_model = int(config["d_model"])
    n_heads = int(config["n_heads"])
    d_ff = int(config["d_ff"])
    e_layers = int(config["e_layers"])
    patch_len = int(config["patch_len"])
    num_patches = seq_len // patch_len
    token_count = channels * num_patches
    head_dim = d_model // n_heads
    patch_parameters = patch_len * d_model + d_model
    block_parameters = (
        2 * head_dim**2
        + 2 * head_dim
        + 6 * token_count
        + d_model**2
        + 6 * d_model
        + 2 * d_model * d_ff
        + d_ff
    )
    head_parameters = pred_len * d_model * num_patches + pred_len
    return patch_parameters + e_layers * block_parameters + head_parameters


def validate_timefilter_config(config: dict[str, Any]) -> dict[str, Any]:
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["c_out"])
    d_model = int(config["d_model"])
    n_heads = int(config["n_heads"])
    d_ff = int(config["d_ff"])
    e_layers = int(config["e_layers"])
    patch_len = int(config["patch_len"])
    alpha = float(config["alpha"])
    top_p = float(config["top_p"])
    pos = bool(config["pos"])
    dropout = float(config["dropout"])
    if min(seq_len, pred_len, channels, d_model, n_heads, d_ff, e_layers, patch_len) < 1:
        raise ValueError("invalid TimeFilter positive geometry")
    if patch_len > seq_len:
        raise ValueError("TimeFilter requires patch_len <= seq_len")
    if seq_len % patch_len != 0:
        raise ValueError("TimeFilter requires seq_len divisible by patch_len")
    if d_model % 2 != 0:
        raise ValueError("TimeFilter requires even d_model for positional embedding")
    if d_model % n_heads != 0:
        raise ValueError("TimeFilter requires d_model divisible by n_heads")
    if not 0.0 <= alpha <= 1.0 or not 0.0 <= top_p <= 1.0:
        raise ValueError("TimeFilter alpha and top_p must be in [0, 1]")
    if not 0.0 <= dropout < 1.0:
        raise ValueError("TimeFilter dropout must be in [0, 1)")
    num_patches = seq_len // patch_len
    token_count = channels * num_patches
    if token_count > TIMEFILTER_POSITIONAL_LIMIT:
        raise ValueError("TimeFilter token count exceeds positional limit 10000")
    return {
        "seq_len": seq_len,
        "pred_len": pred_len,
        "channels": channels,
        "d_model": d_model,
        "n_heads": n_heads,
        "head_dim": d_model // n_heads,
        "d_ff": d_ff,
        "e_layers": e_layers,
        "patch_len": patch_len,
        "stride": patch_len,
        "num_patches": num_patches,
        "token_count": token_count,
        "mask_shape": [token_count, TIMEFILTER_EXPERT_COUNT, token_count],
        "same_time_region_size": channels - 1,
        "same_channel_region_size": num_patches - 1,
        "cross_region_size": (channels - 1) * (num_patches - 1),
        "alpha": alpha,
        "knn_zero_count": int(alpha * token_count),
        "top_p": top_p,
        "noisy_gating": top_p > 0.0,
        "positional_embedding": pos,
        "positional_limit": TIMEFILTER_POSITIONAL_LIMIT,
        "dropout": dropout,
        "expected_parameter_count": expected_parameter_count(config),
    }


def timefilter_config(request: ProviderRequest) -> dict[str, Any]:
    config = {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "pred_len": request.pred_len,
        "c_out": request.channels,
        "enc_in": request.channels,
        "d_model": request.d_model,
        "d_ff": request.timefilter_d_ff,
        "patch_len": request.timefilter_patch_len,
        "alpha": request.timefilter_alpha,
        "top_p": request.timefilter_top_p,
        "pos": request.timefilter_pos,
        "n_heads": request.timefilter_n_heads,
        "e_layers": request.e_layers,
        "dropout": request.dropout,
        "num_class": 1,
    }
    validate_timefilter_config(config)
    return config


def build_timefilter(source_root: Path, config: dict[str, Any]) -> Any:
    return load_timefilter(source_root)(SimpleNamespace(**config))


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


def verify_mask_geometry(model: Any, geometry: dict[str, Any]) -> None:
    import torch

    mask = model._get_mask(torch.device("cpu"))
    if list(mask.shape) != geometry["mask_shape"]:
        raise ValueError(
            f"TimeFilter mask shape mismatch: expected {geometry['mask_shape']}, "
            f"got {list(mask.shape)}"
        )
    counts = mask.sum(dim=-1)
    expected_counts = torch.tensor(
        [
            geometry["same_time_region_size"],
            geometry["same_channel_region_size"],
            geometry["cross_region_size"],
        ],
        dtype=counts.dtype,
    )
    if not bool((counts == expected_counts).all().item()):
        raise ValueError("TimeFilter graph-mask region counts mismatch")
    if not bool((mask.sum(dim=1).diagonal() == 0).all().item()):
        raise ValueError("TimeFilter graph mask includes self edges")


def verify_model_geometry(model: Any, geometry: dict[str, Any], *, strict: bool) -> None:
    observed = {
        "seq_len": int(model.seq_len),
        "pred_len": int(model.pred_len),
        "channels": int(model.n_vars),
        "d_model": int(model.dim),
        "d_ff": int(model.d_ff),
        "patch_len": int(model.patch_len),
        "stride": int(model.stride),
        "num_patches": int(model.num_patches),
        "e_layers": int(model.backbone.n_blocks),
    }
    expected = {key: geometry[key] for key in observed}
    if observed != expected:
        raise ValueError(f"TimeFilter geometry mismatch: expected {expected}, got {observed}")
    if not strict:
        return
    blocks = list(model.backbone.blocks)
    if len(blocks) != geometry["e_layers"]:
        raise ValueError("TimeFilter graph-block count mismatch")
    for block in blocks:
        graph_filter = block.gnn
        if int(graph_filter.n_heads) != geometry["n_heads"]:
            raise ValueError("TimeFilter n_heads mismatch")
        gate = graph_filter.graph_learner.mask_moe.gate
        noise = graph_filter.graph_learner.mask_moe.noise
        if gate.in_features != geometry["token_count"] or gate.out_features != 3:
            raise ValueError("TimeFilter gate geometry mismatch")
        if noise.in_features != geometry["token_count"] or noise.out_features != 3:
            raise ValueError("TimeFilter noise geometry mismatch")
    verify_mask_geometry(model, geometry)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count != geometry["expected_parameter_count"]:
        raise ValueError(
            "TimeFilter parameter count mismatch: "
            f"expected {geometry['expected_parameter_count']}, got {parameter_count}"
        )


def fit_save(request: ProviderRequest) -> ProviderResponse:
    import torch

    identity = source_evidence(request)
    seed_everything(request.seed)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    config = timefilter_config(request)
    geometry = validate_timefilter_config(config)
    model = build_timefilter(request.source_root, config).to("cpu")
    verify_model_geometry(
        model,
        geometry,
        strict=request.source_policy == SourcePolicy.PINNED,
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
        prediction_tensor = model(x, None, None, None)
        loss = torch.mean((prediction_tensor - target) ** 2)
        if not torch.isfinite(loss).item():
            raise ValueError("TimeFilter training loss is non-finite")
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    model.eval()
    with torch.no_grad():
        prediction_tensor = model(x, None, None, None)
        prediction = prediction_tensor.cpu().numpy()
    expected = (2, request.pred_len, request.channels)
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid TimeFilter prediction: {prediction.shape}")
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
            "model_name": "TimeFilter",
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
        model_name="TimeFilter",
        artifacts={
            "checkpoint": str(checkpoint),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            **runtime_evidence(),
            "model_class": "models.TimeFilter.Model",
            "effective_config": config,
            "graph_geometry": geometry,
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
    if checkpoint.get("model_name") != "TimeFilter":
        raise ValueError("checkpoint model mismatch: expected TimeFilter")
    config = checkpoint["config"]
    geometry = validate_timefilter_config(config)
    if checkpoint.get("geometry") != geometry:
        raise ValueError("checkpoint TimeFilter geometry mismatch")
    model = build_timefilter(request.source_root, config).to("cpu")
    verify_model_geometry(
        model,
        geometry,
        strict=request.source_policy == SourcePolicy.PINNED,
    )
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    with np.load(request.input_path) as payload:
        x = torch.from_numpy(payload["x"]).to(dtype=torch.float32)
    expected_input = (2, geometry["seq_len"], geometry["channels"])
    if tuple(x.shape) != expected_input:
        raise ValueError(
            "invalid TimeFilter input shape: "
            f"expected {expected_input}, got {tuple(x.shape)}"
        )
    with torch.no_grad():
        prediction_tensor = model(x, None, None, None)
        prediction = prediction_tensor.cpu().numpy()
    expected = (2, geometry["pred_len"], geometry["channels"])
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid reloaded TimeFilter prediction: {prediction.shape}")
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    if parameter_devices != ["cpu"]:
        raise ValueError(f"unexpected parameter devices: {parameter_devices}")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    after_path = request.output_dir / "prediction_after.npy"
    atomic_numpy(after_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name="TimeFilter",
        artifacts={"prediction_after": str(after_path)},
        evidence={
            **runtime_evidence(),
            "model_class": "models.TimeFilter.Model",
            "graph_geometry": geometry,
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
