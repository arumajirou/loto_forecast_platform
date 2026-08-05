from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ID = "thuml/sundial-base-128m"
REVISION = "3212e42564493f520593e5414af4367fc4b49226"
REMOTE_CODE_REVIEW_PATH = (
    PROJECT_ROOT / "audit" / "tsfm-runtime" / "sundial-base" / "remote-code-review.json"
)
DEFAULT_QUANTILE_LEVELS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
REQUIRED_REMOTE_CODE_FILES = {
    "configuration_sundial.py",
    "flow_loss.py",
    "modeling_sundial.py",
    "ts_generation_mixin.py",
}


class SundialProviderRuntimeError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quantile_key(level: float) -> str:
    return f"q{level:.6f}".rstrip("0").rstrip(".")


def _normalize_quantile_levels(value: Any) -> tuple[float, ...]:
    if value is None:
        return DEFAULT_QUANTILE_LEVELS
    if not isinstance(value, (list, tuple)) or not value:
        raise SundialProviderRuntimeError(
            "INVALID_REQUEST",
            "quantile_levels must be a non-empty list",
        )
    levels = tuple(float(item) for item in value)
    if not all(np.isfinite(level) and 0.0 <= level <= 1.0 for level in levels):
        raise SundialProviderRuntimeError(
            "INVALID_REQUEST",
            "quantile_levels must contain finite values in [0, 1]",
        )
    if any(left >= right for left, right in zip(levels, levels[1:], strict=False)):
        raise SundialProviderRuntimeError(
            "INVALID_REQUEST",
            "quantile_levels must be strictly increasing",
        )
    return levels


def _normalize_num_samples(value: Any) -> int:
    if isinstance(value, bool):
        raise SundialProviderRuntimeError("INVALID_REQUEST", "num_samples must be an integer")
    try:
        num_samples = int(value)
    except (TypeError, ValueError) as exc:
        raise SundialProviderRuntimeError(
            "INVALID_REQUEST",
            "num_samples must be an integer",
        ) from exc
    if not 1 <= num_samples <= 100:
        raise SundialProviderRuntimeError(
            "INVALID_REQUEST",
            "num_samples must be in the inclusive range 1..100",
        )
    return num_samples


def _normalize_samples(
    samples: Any,
    *,
    expected_series_count: int,
    expected_num_samples: int,
    expected_horizon: int,
) -> np.ndarray:
    if hasattr(samples, "detach"):
        samples = samples.detach().cpu().numpy()
    array = np.asarray(samples, dtype=np.float64)
    expected = (expected_series_count, expected_num_samples, expected_horizon)
    if array.shape != expected:
        raise SundialProviderRuntimeError(
            "INVALID_PREDICTION",
            f"sample shape mismatch: expected={expected}, actual={array.shape}",
        )
    if not np.isfinite(array).all():
        raise SundialProviderRuntimeError(
            "INVALID_PREDICTION",
            "generated samples contain NaN or Inf",
        )
    return array


def _summarize_samples(
    samples: np.ndarray,
    quantile_levels: tuple[float, ...],
) -> tuple[dict[str, list[list[float]]], dict[str, list[list[float]]]]:
    statistics = {
        "mean": np.mean(samples, axis=1).tolist(),
        "median": np.median(samples, axis=1).tolist(),
        "std": np.std(samples, axis=1, ddof=0).tolist(),
    }
    quantile_array = np.quantile(samples, quantile_levels, axis=1)
    if np.any(np.diff(quantile_array, axis=0) < 0.0):
        raise SundialProviderRuntimeError(
            "INVALID_PREDICTION",
            "empirical quantiles are not monotonic",
        )
    quantiles = {
        _quantile_key(level): quantile_array[index].tolist()
        for index, level in enumerate(quantile_levels)
    }
    return statistics, quantiles


def _select_point_forecast(
    statistics: dict[str, list[list[float]]],
    point_strategy: str,
) -> np.ndarray:
    if point_strategy not in {"mean", "median"}:
        raise SundialProviderRuntimeError(
            "INVALID_REQUEST",
            "point_strategy must be 'mean' or 'median'",
        )
    point = np.asarray(statistics[point_strategy], dtype=np.float64)
    if point.ndim != 2 or not np.isfinite(point).all():
        raise SundialProviderRuntimeError(
            "INVALID_PREDICTION",
            "point forecast must be a finite [series, horizon] array",
        )
    return point


def _snapshot(
    repo_id: str,
    revision: str,
    local_files_only: bool,
    snapshot: str | None,
) -> Path:
    if snapshot:
        snapshot_path = Path(snapshot).expanduser().resolve()
        if not snapshot_path.is_dir():
            raise SundialProviderRuntimeError(
                "MODEL_WEIGHTS_MISSING",
                f"snapshot_path does not exist: {snapshot_path}",
            )
    else:
        from huggingface_hub import snapshot_download

        snapshot_path = Path(
            snapshot_download(
                repo_id=repo_id,
                revision=revision,
                local_files_only=local_files_only,
                allow_patterns=[
                    "*.json",
                    "*.safetensors",
                    "*.bin",
                    "*.py",
                    "*.txt",
                    "README.md",
                    "LICENSE*",
                ],
            )
        ).resolve()
    if snapshot_path.name != revision:
        raise SundialProviderRuntimeError(
            "REVISION_MISMATCH",
            f"snapshot directory does not match pinned revision: {snapshot_path}",
        )
    return snapshot_path


def _load_reviewed_remote_code_sha256(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SundialProviderRuntimeError(
            "REMOTE_CODE_REVIEW_MISSING",
            f"remote-code review does not exist: {path}",
        )
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SundialProviderRuntimeError(
            "REMOTE_CODE_REVIEW_INVALID",
            f"remote-code review is invalid: {exc}",
        ) from exc
    expected_identity = {
        "model_id": "sundial-base",
        "repo_id": REPO_ID,
        "revision": REVISION,
    }
    for key, expected in expected_identity.items():
        if review.get(key) != expected:
            raise SundialProviderRuntimeError(
                "REMOTE_CODE_REVIEW_INVALID",
                f"remote-code review {key} mismatch",
            )
    if review.get("review_status") != "APPROVED":
        raise SundialProviderRuntimeError(
            "REMOTE_CODE_REVIEW_NOT_APPROVED",
            "remote-code review is not APPROVED",
        )
    rows = review.get("files")
    if not isinstance(rows, list) or not rows:
        raise SundialProviderRuntimeError(
            "REMOTE_CODE_REVIEW_INVALID",
            "remote-code review files are missing",
        )
    approved: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("name") or not row.get("sha256"):
            raise SundialProviderRuntimeError(
                "REMOTE_CODE_REVIEW_INVALID",
                "remote-code review contains an invalid file row",
            )
        approved[Path(str(row["name"])).name] = str(row["sha256"]).lower()
    return approved


def _approved_remote_code_sha256(request: dict[str, Any]) -> dict[str, str]:
    raw = request.get("approved_remote_code_sha256")
    if not isinstance(raw, dict) or not raw:
        raise SundialProviderRuntimeError(
            "REMOTE_CODE_REVIEW_MISSING",
            "approved_remote_code_sha256 is required",
        )
    approved: dict[str, str] = {}
    for name, digest in raw.items():
        normalized_name = Path(str(name)).name
        normalized_digest = str(digest).lower()
        if len(normalized_digest) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_digest
        ):
            raise SundialProviderRuntimeError(
                "REMOTE_CODE_REVIEW_INVALID",
                f"invalid SHA-256 for remote code file: {normalized_name}",
            )
        approved[normalized_name] = normalized_digest
    return approved


def _verify_remote_code(
    snapshot_path: Path,
    approved_sha256: dict[str, str],
) -> dict[str, str]:
    remote_code = sorted(snapshot_path.glob("*.py"))
    actual_names = {path.name for path in remote_code}
    missing_required = sorted(REQUIRED_REMOTE_CODE_FILES - actual_names)
    if missing_required:
        raise SundialProviderRuntimeError(
            "PARTIAL_SNAPSHOT",
            f"required remote code files are missing: {missing_required}",
        )
    actual: dict[str, str] = {}
    for path in remote_code:
        if path.name not in approved_sha256:
            raise SundialProviderRuntimeError(
                "REMOTE_CODE_HASH_MISMATCH",
                f"unreviewed remote code file found: {path.name}",
            )
        digest = _sha256(path)
        if digest != approved_sha256[path.name]:
            raise SundialProviderRuntimeError(
                "REMOTE_CODE_HASH_MISMATCH",
                f"remote code SHA-256 mismatch: {path.name}",
            )
        actual[path.name] = digest
    return actual


def _validate_identity(request: dict[str, Any]) -> tuple[str, str]:
    repo_id = str(request.get("repo_id", REPO_ID))
    revision = str(request.get("revision") or REVISION)
    if repo_id != REPO_ID:
        raise SundialProviderRuntimeError(
            "MODEL_IDENTITY_MISMATCH",
            f"unsupported repo_id: {repo_id}",
        )
    if revision != REVISION:
        raise SundialProviderRuntimeError(
            "REVISION_MISMATCH",
            f"unsupported revision: {revision}",
        )
    return repo_id, revision


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    repo_id, revision = _validate_identity(request)
    if request.get("local_files_only", True) is not True:
        raise SundialProviderRuntimeError(
            "OFFLINE_MODE_REQUIRED",
            "local_files_only must be true",
        )
    requested_device = str(request.get("device", "cpu"))
    if requested_device not in {"cpu", "cuda"}:
        raise SundialProviderRuntimeError(
            "INVALID_REQUEST",
            f"unsupported device: {requested_device}",
        )
    dtype = str(request.get("dtype", "float32"))
    if dtype != "float32":
        raise SundialProviderRuntimeError(
            "UNSUPPORTED_PRECISION",
            f"Sundial provider v2 supports only float32, got {dtype}",
        )
    horizon = int(request.get("prediction_length", 1))
    if horizon != 1:
        raise SundialProviderRuntimeError(
            "UNSUPPORTED_HORIZON",
            "provider v2 phase PR-SD1 supports prediction_length=1 only",
        )
    num_samples = _normalize_num_samples(request.get("num_samples", 3))
    quantile_levels = _normalize_quantile_levels(request.get("quantile_levels"))
    point_strategy = str(request.get("point_strategy", "median"))
    revin = request.get("revin", True)
    if not isinstance(revin, bool):
        raise SundialProviderRuntimeError("INVALID_REQUEST", "revin must be a boolean")

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    if requested_device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch
    from transformers import AutoModelForCausalLM

    cuda_available = torch.cuda.is_available()
    if requested_device == "cuda" and not cuda_available:
        raise SundialProviderRuntimeError(
            "CPU_FALLBACK_FORBIDDEN",
            "CUDA was requested but torch.cuda.is_available() is false",
        )
    execution_device = requested_device
    if execution_device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    snapshot_path = _snapshot(
        repo_id,
        revision,
        bool(request.get("local_files_only", True)),
        request.get("snapshot_path"),
    )
    config_path = snapshot_path / "config.json"
    weights = sorted(snapshot_path.glob("*.safetensors")) + sorted(
        snapshot_path.glob("*.bin")
    )
    if not config_path.is_file():
        raise SundialProviderRuntimeError(
            "PARTIAL_SNAPSHOT",
            f"config.json is missing from {snapshot_path}",
        )
    if not weights:
        raise SundialProviderRuntimeError(
            "MODEL_WEIGHTS_MISSING",
            f"no model weights found in {snapshot_path}",
        )
    reviewed_remote_code = _load_reviewed_remote_code_sha256(
        REMOTE_CODE_REVIEW_PATH
    )
    requested_remote_code = _approved_remote_code_sha256(request)
    if requested_remote_code != reviewed_remote_code:
        raise SundialProviderRuntimeError(
            "REMOTE_CODE_REVIEW_INVALID",
            "request allowlist does not match the checked-in remote-code review",
        )
    remote_code_sha256 = _verify_remote_code(snapshot_path, reviewed_remote_code)

    model = AutoModelForCausalLM.from_pretrained(
        str(snapshot_path),
        trust_remote_code=True,
        local_files_only=True,
        torch_dtype=torch.float32,
        device_map=None,
    ).to(execution_device)
    model.eval()

    history = pd.DataFrame(request["history"])
    position_columns = [f"n{position}" for position in range(1, 8)]
    missing_columns = sorted(set(position_columns) - set(history.columns))
    if missing_columns:
        raise SundialProviderRuntimeError(
            "INVALID_REQUEST",
            f"history is missing position columns: {missing_columns}",
        )
    context = torch.tensor(
        history[position_columns].to_numpy(dtype=np.float32).T,
        dtype=torch.float32,
        device=execution_device,
    )
    seed = int(request.get("seed", 42))
    np.random.seed(seed)
    torch.manual_seed(seed)
    if execution_device == "cuda":
        torch.cuda.manual_seed_all(seed)

    with torch.no_grad():
        generated = model.generate(
            inputs=context,
            max_length=context.shape[1] + horizon,
            num_samples=num_samples,
            revin=revin,
        )
    samples = _normalize_samples(
        generated,
        expected_series_count=len(position_columns),
        expected_num_samples=num_samples,
        expected_horizon=horizon,
    )
    statistics, quantiles = _summarize_samples(samples, quantile_levels)
    point_forecast = _select_point_forecast(statistics, point_strategy)
    predictions = point_forecast[:, 0]
    gpu_used = execution_device == "cuda"

    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 2,
        "repo_id": repo_id,
        "revision": revision,
        "snapshot_path": str(snapshot_path),
        "predictions": predictions.tolist(),
        "prediction_shape": list(predictions.shape),
        "finite": True,
        "samples": samples.tolist(),
        "samples_shape": list(samples.shape),
        "sample_statistics": statistics,
        "point_forecasts": {
            "mean": statistics["mean"],
            "median": statistics["median"],
        },
        "point_strategy": point_strategy,
        "quantiles": quantiles,
        "quantile_levels": list(quantile_levels),
        "quantile_source": "EMPIRICAL_FROM_GENERATED_SAMPLES",
        "properties": {
            "library": "transformers",
            "package": "transformers",
            "transformers_version": importlib.metadata.version("transformers"),
            "torch_version": torch.__version__,
            "license": "apache-2.0",
            "backend": "torch",
            "trust_remote_code": True,
            "remote_code_revision": revision,
            "remote_code_sha256": remote_code_sha256,
            "approved_remote_code_sha256": reviewed_remote_code,
            "loaded_from_resolved_snapshot": True,
            "offline_mode": True,
            "context_length": int(context.shape[1]),
            "prediction_length": horizon,
            "num_samples": num_samples,
            "random_seed": seed,
            "revin": revin,
            "point_strategy": point_strategy,
            "quantile_levels": list(quantile_levels),
            "quantile_source": "EMPIRICAL_FROM_GENERATED_SAMPLES",
            "model_architecture": "SundialForPrediction",
            "weight_files": [path.name for path in weights],
            "weight_sha256": {path.name: _sha256(path) for path in weights},
            "config_sha256": _sha256(config_path),
            "snapshot_complete": True,
        },
        "gpu_evidence": {
            "requested_device": requested_device,
            "execution_device": execution_device,
            "cuda_available": cuda_available,
            "gpu_requested": requested_device == "cuda",
            "gpu_used": gpu_used,
            "gpu_certification": "OBSERVED" if gpu_used else "NOT_CERTIFIED",
            "resource_certification": "GPU_PASS" if gpu_used else "CPU_ONLY_PASS",
            "cpu_fallback": False,
            "fallback_reason": None,
            "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if gpu_used else 0,
            "gpu_pid": os.getpid() if gpu_used else None,
        },
        "artifact_reference": {
            "repo_id": repo_id,
            "revision": revision,
            "snapshot_path": str(snapshot_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Sundial provider in an isolated env")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    try:
        response = run_provider(_load_payload(args.request))
    except SundialProviderRuntimeError as exc:
        response = {
            "status": exc.status,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    except Exception as exc:
        response = {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    _write_payload(args.response, response)


if __name__ == "__main__":
    main()
