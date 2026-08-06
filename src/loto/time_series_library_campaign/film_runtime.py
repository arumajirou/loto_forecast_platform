from __future__ import annotations

import importlib
import os
import platform
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np

from .contracts import ProviderRequest, ProviderResponse, ProviderStatus, SourcePolicy
from .data import atomic_numpy, git_blob_sha, sha256_file
from .runtime import seed_everything, source_path

PINNED_FILM_GIT_BLOB = "1240e37047f26b0fd905151f0b2671255b6ec045"
FILM_HIPPO_ORDER = 256
FILM_MULTISCALE = (1, 2, 4)
FILM_WINDOW_SIZE = (FILM_HIPPO_ORDER,)


def verify_pinned_film_source(source_root: Path) -> dict[str, Any]:
    path = source_root / "models" / "FiLM.py"
    if not path.is_file():
        raise ValueError("missing models/FiLM.py")
    actual = git_blob_sha(path)
    if actual != PINNED_FILM_GIT_BLOB:
        raise ValueError(
            f"pinned source mismatch: models/FiLM.py: expected {PINNED_FILM_GIT_BLOB}, "
            f"got {actual}"
        )
    return {
        "status": "VERIFIED",
        "policy": "pinned",
        "model_name": "FiLM",
        "files": {
            "models/FiLM.py": {
                "expected_git_blob_sha": PINNED_FILM_GIT_BLOB,
                "actual_git_blob_sha": actual,
                "sha256": sha256_file(path),
            }
        },
    }


def source_evidence(request: ProviderRequest) -> dict[str, Any]:
    if request.source_policy == SourcePolicy.TEST_FIXTURE:
        return {"status": "TEST_FIXTURE", "policy": "test_fixture", "model_name": "FiLM"}
    return verify_pinned_film_source(request.source_root)


def ensure_cpu_only_runtime() -> None:
    import torch

    if torch.cuda.is_available():
        raise ValueError(
            "FiLM CPU lane requires CUDA unavailable because pinned source binds buffers globally"
        )


def load_film_module(source_root: Path) -> ModuleType:
    ensure_cpu_only_runtime()
    with source_path(source_root):
        module = importlib.import_module("models.FiLM")
        if getattr(module, "Model", None) is None:
            raise AttributeError("models.FiLM does not expose class Model")
        source_device = str(getattr(module, "device", "unknown"))
        if source_device != "cpu":
            raise ValueError(f"FiLM pinned source selected non-CPU global device: {source_device}")
        return module


def film_config(request: ProviderRequest) -> dict[str, Any]:
    return {
        "task_name": "long_term_forecast",
        "seq_len": request.seq_len,
        "label_len": 0,
        "pred_len": request.pred_len,
        "e_layers": request.e_layers,
        "enc_in": request.channels,
        "d_model": request.d_model,
        "c_out": request.channels,
        "dropout": request.dropout,
        "num_class": 1,
    }


def expected_parameter_count(config: dict[str, Any]) -> int:
    channels = int(config["enc_in"])
    modes = min(32, min(int(config["pred_len"]), int(config["seq_len"])) // 2)
    spectral = len(FILM_MULTISCALE) * 2 * FILM_HIPPO_ORDER**2 * modes
    affine = 2 * channels
    mixer = len(FILM_MULTISCALE) + 1
    return spectral + affine + mixer


def validate_film_config(config: dict[str, Any]) -> dict[str, Any]:
    seq_len = int(config["seq_len"])
    pred_len = int(config["pred_len"])
    channels = int(config["enc_in"])
    e_layers = int(config["e_layers"])
    dropout = float(config["dropout"])
    if pred_len < 2:
        raise ValueError("FiLM certified lane requires pred_len >= 2")
    if seq_len < 4 * pred_len:
        raise ValueError("FiLM certified lane requires seq_len >= 4 * pred_len")
    if channels < 1:
        raise ValueError("FiLM certified lane requires channels >= 1")
    if e_layers != 1:
        raise ValueError("FiLM certified lane requires e_layers=1")
    if dropout != 0.0:
        raise ValueError("FiLM certified lane requires dropout=0.0")
    modes = min(32, pred_len // 2)
    if modes < 1:
        raise ValueError("FiLM certified lane requires at least one spectral mode")
    eval_shapes = [[pred_len * scale, FILM_HIPPO_ORDER] for scale in FILM_MULTISCALE]
    return {
        "seq_len": seq_len,
        "pred_len": pred_len,
        "channels": channels,
        "e_layers": 1,
        "dropout": 0.0,
        "hippo_order": FILM_HIPPO_ORDER,
        "multiscale": list(FILM_MULTISCALE),
        "window_size": list(FILM_WINDOW_SIZE),
        "required_input_lengths": [pred_len * scale for scale in FILM_MULTISCALE],
        "spectral_modes": modes,
        "eval_matrix_shapes": eval_shapes,
        "global_device_policy": "cpu_only_interpreter",
        "scipy_required": True,
        "expected_parameter_count": expected_parameter_count(config),
    }


def build_film(source_root: Path, config: dict[str, Any]) -> tuple[Any, ModuleType]:
    module = load_film_module(source_root)
    return module.Model(SimpleNamespace(**config)), module


def verify_model_geometry(model: Any, module: ModuleType, geometry: dict[str, Any]) -> None:
    observed = {
        "seq_len": int(model.seq_len),
        "pred_len": int(model.pred_len),
        "channels": int(model.enc_in),
        "e_layers": int(model.e_layers),
        "multiscale": list(model.multiscale),
        "window_size": list(model.window_size),
    }
    expected = {key: geometry[key] for key in observed}
    if observed != expected:
        raise ValueError(f"FiLM geometry mismatch: expected {expected}, got {observed}")
    if str(module.device) != "cpu":
        raise ValueError(f"FiLM global source device mismatch: {module.device}")
    if len(model.legts) != len(FILM_MULTISCALE):
        raise ValueError("FiLM HiPPO module count mismatch")
    if len(model.spec_conv_1) != len(FILM_MULTISCALE):
        raise ValueError("FiLM spectral module count mismatch")
    for index, legt in enumerate(model.legts):
        if int(legt.N) != FILM_HIPPO_ORDER:
            raise ValueError("FiLM HiPPO order mismatch")
        if list(legt.eval_matrix.shape) != geometry["eval_matrix_shapes"][index]:
            raise ValueError("FiLM evaluation matrix shape mismatch")
    for spectral in model.spec_conv_1:
        if int(spectral.modes) != geometry["spectral_modes"]:
            raise ValueError("FiLM spectral mode count mismatch")
        expected_shape = (
            FILM_HIPPO_ORDER,
            FILM_HIPPO_ORDER,
            geometry["spectral_modes"],
        )
        if tuple(spectral.weights_real.shape) != expected_shape:
            raise ValueError("FiLM real spectral weight shape mismatch")
        if tuple(spectral.weights_imag.shape) != expected_shape:
            raise ValueError("FiLM imaginary spectral weight shape mismatch")
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count != geometry["expected_parameter_count"]:
        raise ValueError(
            "FiLM parameter count mismatch: "
            f"expected {geometry['expected_parameter_count']}, got {parameter_count}"
        )
    buffer_devices = sorted({str(buffer.device) for buffer in model.buffers()})
    if buffer_devices != ["cpu"]:
        raise ValueError(f"unexpected FiLM buffer devices: {buffer_devices}")


def runtime_evidence() -> dict[str, Any]:
    import scipy
    import torch

    return {
        "process_id": os.getpid(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "device": "cpu",
        "cuda_available": bool(torch.cuda.is_available()),
        "cpu_fallback": False,
    }


def fit_save(request: ProviderRequest) -> ProviderResponse:
    import torch

    ensure_cpu_only_runtime()
    identity = source_evidence(request)
    seed_everything(request.seed)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    config = film_config(request)
    geometry = validate_film_config(config)
    model, module = build_film(request.source_root, config)
    model = model.to("cpu")
    verify_model_geometry(model, module, geometry)
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
            raise ValueError("FiLM training loss is non-finite")
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
    model.eval()
    with torch.no_grad():
        prediction_tensor = model(x, None, None, None)
        prediction = prediction_tensor.cpu().numpy()
    expected = (2, request.pred_len, request.channels)
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid FiLM prediction: {prediction.shape}")
    state = model.state_dict()
    if not state or not all(torch.isfinite(value).all().item() for value in state.values()):
        raise ValueError("FiLM state_dict is missing or non-finite")
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    buffer_devices = sorted({str(buffer.device) for buffer in model.buffers()})
    if parameter_devices != ["cpu"] or buffer_devices != ["cpu"]:
        raise ValueError(
            f"unexpected FiLM devices: parameters={parameter_devices}, buffers={buffer_devices}"
        )
    checkpoint_path = request.output_dir / "checkpoint.pt"
    with tempfile.NamedTemporaryFile(mode="wb", dir=request.output_dir, delete=False) as handle:
        temporary = Path(handle.name)
    torch.save(
        {"state_dict": state, "config": config, "geometry": geometry, "model_name": "FiLM"},
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
        model_name="FiLM",
        artifacts={
            "checkpoint": str(checkpoint_path),
            "input": str(input_path),
            "prediction_before": str(before_path),
        },
        evidence={
            **runtime_evidence(),
            "model_class": "models.FiLM.Model",
            "effective_config": config,
            "geometry": geometry,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "finite_state_dict": True,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "parameter_devices": parameter_devices,
            "buffer_devices": buffer_devices,
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
    ensure_cpu_only_runtime()
    identity = source_evidence(request)
    seed_everything(request.seed)
    checkpoint = torch.load(request.checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint.get("model_name") != "FiLM":
        raise ValueError("checkpoint model mismatch: expected FiLM")
    config = checkpoint["config"]
    geometry = validate_film_config(config)
    if checkpoint.get("geometry") != geometry:
        raise ValueError("checkpoint FiLM geometry mismatch")
    model, module = build_film(request.source_root, config)
    model = model.to("cpu")
    verify_model_geometry(model, module, geometry)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    with np.load(request.input_path) as payload:
        x = torch.from_numpy(payload["x"]).to(dtype=torch.float32)
    expected_input = (2, geometry["seq_len"], geometry["channels"])
    if tuple(x.shape) != expected_input:
        raise ValueError(
            f"invalid FiLM input shape: expected {expected_input}, got {tuple(x.shape)}"
        )
    with torch.no_grad():
        prediction_tensor = model(x, None, None, None)
        prediction = prediction_tensor.cpu().numpy()
    expected = (2, geometry["pred_len"], geometry["channels"])
    if prediction.shape != expected or not np.isfinite(prediction).all():
        raise ValueError(f"invalid reloaded FiLM prediction: {prediction.shape}")
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    buffer_devices = sorted({str(buffer.device) for buffer in model.buffers()})
    if parameter_devices != ["cpu"] or buffer_devices != ["cpu"]:
        raise ValueError(
            f"unexpected FiLM devices: parameters={parameter_devices}, buffers={buffer_devices}"
        )
    request.output_dir.mkdir(parents=True, exist_ok=True)
    after_path = request.output_dir / "prediction_after.npy"
    atomic_numpy(after_path, lambda handle: np.save(handle, prediction))
    return ProviderResponse(
        status=ProviderStatus.PASS,
        operation=request.operation,
        model_name="FiLM",
        artifacts={"prediction_after": str(after_path)},
        evidence={
            **runtime_evidence(),
            "model_class": "models.FiLM.Model",
            "geometry": geometry,
            "prediction_shape": list(prediction.shape),
            "finite_prediction": True,
            "strict_state_load": True,
            "parameter_devices": parameter_devices,
            "buffer_devices": buffer_devices,
            "input_device": str(x.device),
            "output_device": str(prediction_tensor.device),
            "source_identity": identity,
            "prediction_sha256": sha256_file(after_path),
        },
    )
