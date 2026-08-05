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

PINNED_TSMIXER_GIT_BLOB = "76884d467f17d64aa87d8e22cc9f0aa6231914cf"


def verify_pinned_tsmixer_source(source_root: Path) -> dict[str, Any]:
    path = source_root / "models/TSMixer.py"
    if not path.is_file():
        raise ValueError("missing pinned source file: models/TSMixer.py")
    actual = git_blob_sha(path)
    if actual != PINNED_TSMIXER_GIT_BLOB:
        raise ValueError(
            "pinned source mismatch: models/TSMixer.py: "
            f"expected {PINNED_TSMIXER_GIT_BLOB}, got {actual}"
        )
    return {
        "status": "VERIFIED",
        "policy": "pinned",
        "model_name": "TSMixer",
        "files": {
            "models/TSMixer.py": {
                "expected_git_blob_sha": PINNED_TSMIXER_GIT_BLOB,
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
            "model_name": "TSMixer",
        }
    return verify_pinned_tsmixer_source(request.source_root)


def load_tsmixer(source_root: Path) -> type[Any]:
    with source_path(source_root):
        model_class = getattr(importlib.import_module("models.TSMixer"), "Model", None)
        if model_class is None:
            raise AttributeError("models.TSMixer does not expose class Model")
        return model_class


def tsmixer_config(request: ProviderRequest) -> dict[str, Any]:
    return {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "pred_len": request.pred_len,
        "enc_in": request.channels,
        "num_class": 1,
        "d_model": request.d_model,
        "dropout": request.dropout,
        "e_layers": request.e_layers,
    }


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
    config = tsmixer_config(request)
    model = load_tsmixer(request.source_root)(SimpleNamespace(**config)).to("cpu")
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
    state = model.state_dict()
    if not state or not all(torch.isfinite(value).all().item() for value in state.values()):
        raise ValueError("state_dict is missing or non-finite")
    checkpoint = request.output_dir / "checkpoint.pt"
    with tempfile.NamedTemporaryFile(mode="wb", dir=request.output_dir, delete=False) as handle:
        temporary = Path(handle.name)
    torch.save(
        {"state_dict": state, "config": config, "model_name": "TSMixer"},
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
        model_name="TSMixer",
        artifacts={
            "checkpoint": str(checkpoint),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            **runtime_evidence(),
            "model_class": "models.TSMixer.Model",
            "effective_config": config,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "finite_state_dict": True,
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
    if checkpoint.get("model_name") != "TSMixer":
        raise ValueError("checkpoint model mismatch: expected TSMixer")
    model = load_tsmixer(request.source_root)(SimpleNamespace(**checkpoint["config"]))
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    with np.load(request.input_path) as payload:
        x = torch.from_numpy(payload["x"]).to(dtype=torch.float32)
    with torch.no_grad():
        prediction = model(x, None, None, None).cpu().numpy()
    if not np.isfinite(prediction).all():
        raise ValueError("reloaded prediction contains NaN or Inf")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    after_path = request.output_dir / "prediction_after.npy"
    atomic_numpy(after_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name="TSMixer",
        artifacts={"prediction_after": str(after_path)},
        evidence={
            **runtime_evidence(),
            "model_class": "models.TSMixer.Model",
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "strict_state_load": True,
            "source_identity": identity,
            "prediction_sha256": sha256_file(after_path),
        },
    )
