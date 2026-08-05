from __future__ import annotations

import importlib
import os
import random
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import numpy as np

from .contracts import ProviderRequest, ProviderResponse, ProviderStatus
from .data import atomic_numpy, sha256_file


@contextmanager
def source_path(source_root: Path) -> Iterator[None]:
    source = str(source_root.resolve())
    sys.path.insert(0, source)
    try:
        yield
    finally:
        if sys.path and sys.path[0] == source:
            sys.path.pop(0)
        for prefix in ("models", "layers"):
            names = [
                key
                for key in sys.modules
                if key == prefix or key.startswith(f"{prefix}.")
            ]
            for name in names:
                sys.modules.pop(name, None)


def load_dlinear(source_root: Path) -> type[Any]:
    with source_path(source_root):
        model_class = getattr(importlib.import_module("models.DLinear"), "Model", None)
        if model_class is None:
            raise AttributeError("models.DLinear does not expose class Model")
        return model_class


def seed_everything(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def dlinear_config(request: ProviderRequest) -> dict[str, Any]:
    moving_avg = min(3, request.seq_len)
    if moving_avg % 2 == 0:
        moving_avg -= 1
    return {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "pred_len": request.pred_len,
        "enc_in": request.channels,
        "moving_avg": max(1, moving_avg),
        "num_class": 1,
    }


def fit_save(request: ProviderRequest) -> ProviderResponse:
    import torch

    seed_everything(request.seed)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    config = dlinear_config(request)
    model = load_dlinear(request.source_root)(SimpleNamespace(**config)).to("cpu")
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
    torch.save({"state_dict": state, "config": config}, temporary)
    os.replace(temporary, checkpoint)
    input_path = request.output_dir / "input.npz"
    before_path = request.output_dir / "prediction_before.npy"
    atomic_numpy(input_path, lambda handle: np.savez(handle, x=x.cpu().numpy()))
    atomic_numpy(before_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name=request.model_name,
        artifacts={
            "checkpoint": str(checkpoint),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            "device": "cpu",
            "cpu_fallback": False,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "finite_state_dict": True,
            "train_steps": request.train_steps,
            "checkpoint_sha256": sha256_file(checkpoint),
            "input_sha256": sha256_file(input_path),
            "prediction_sha256": sha256_file(before_path),
        },
    )


def load_predict(request: ProviderRequest) -> ProviderResponse:
    import torch

    assert request.checkpoint_path is not None
    assert request.input_path is not None
    seed_everything(request.seed)
    checkpoint = torch.load(request.checkpoint_path, map_location="cpu", weights_only=True)
    model = load_dlinear(request.source_root)(SimpleNamespace(**checkpoint["config"]))
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
        model_name=request.model_name,
        artifacts={"prediction_after": str(after_path)},
        evidence={
            "device": "cpu",
            "cpu_fallback": False,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "prediction_sha256": sha256_file(after_path),
        },
    )


def verify_prediction_files(
    before_path: Path,
    after_path: Path,
    *,
    rtol: float = 1e-8,
    atol: float = 1e-8,
) -> dict[str, Any]:
    before = np.load(before_path)
    after = np.load(after_path)
    same_shape = before.shape == after.shape
    finite = bool(np.isfinite(before).all() and np.isfinite(after).all())
    equal = bool(same_shape and finite and np.allclose(before, after, rtol=rtol, atol=atol))
    return {
        "status": "PASS" if equal else "FAIL",
        "same_shape": same_shape,
        "finite": finite,
        "equal_within_tolerance": equal,
        "before_shape": list(before.shape),
        "after_shape": list(after.shape),
        "rtol": rtol,
        "atol": atol,
        "max_abs_error": float(np.max(np.abs(before - after))) if same_shape else None,
        "before_sha256": sha256_file(before_path),
        "after_sha256": sha256_file(after_path),
    }
