from __future__ import annotations

# ruff: noqa: E501
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.models.providers.base import FoundationProvider, FoundationProviderError
from loto.models.providers.subprocess import (
    SubprocessProviderContractError,
    validate_provider_request,
    validate_provider_response,
)

ROOT = Path(__file__).resolve().parents[4]
SUNDIAL_ENV = ROOT / "environments" / "sundial"
SUNDIAL_RUNNER = ROOT / "scripts" / "run_sundial_provider.py"
SUNDIAL_REMOTE_CODE_REVIEW = (
    ROOT / "audit" / "tsfm-runtime" / "sundial-base" / "remote-code-review.json"
)
DEFAULT_QUANTILE_LEVELS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


def _quantile_key(level: float) -> str:
    return f"q{level:.6f}".rstrip("0").rstrip(".")


def _load_remote_code_allowlist(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FoundationProviderError(
            "REMOTE_CODE_REVIEW_MISSING",
            f"missing Sundial remote-code review: {path}",
        )
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FoundationProviderError(
            "REMOTE_CODE_REVIEW_INVALID",
            f"invalid Sundial remote-code review: {exc}",
        ) from exc
    expected_identity = {
        "model_id": "sundial-base",
        "repo_id": "thuml/sundial-base-128m",
        "revision": "3212e42564493f520593e5414af4367fc4b49226",
    }
    for key, expected in expected_identity.items():
        if review.get(key) != expected:
            raise FoundationProviderError(
                "REMOTE_CODE_REVIEW_INVALID",
                f"remote-code review {key} mismatch",
            )
    if review.get("review_status") != "APPROVED":
        raise FoundationProviderError(
            "REMOTE_CODE_REVIEW_NOT_APPROVED",
            "Sundial remote-code review is not APPROVED",
        )
    files = review.get("files")
    if not isinstance(files, list) or not files:
        raise FoundationProviderError(
            "REMOTE_CODE_REVIEW_INVALID",
            "remote-code review files are missing",
        )
    allowlist: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict) or not item.get("name") or not item.get("sha256"):
            raise FoundationProviderError(
                "REMOTE_CODE_REVIEW_INVALID",
                "remote-code review contains an invalid file row",
            )
        allowlist[Path(str(item["name"])).name] = str(item["sha256"]).lower()
    return allowlist


def _normalize_quantile_levels(value: Any) -> tuple[float, ...]:
    if value is None:
        return DEFAULT_QUANTILE_LEVELS
    if not isinstance(value, (list, tuple)) or not value:
        raise FoundationProviderError(
            "INVALID_REQUEST",
            "quantile_levels must be a non-empty list",
        )
    levels = tuple(float(item) for item in value)
    if not all(np.isfinite(level) and 0.0 <= level <= 1.0 for level in levels):
        raise FoundationProviderError(
            "INVALID_REQUEST",
            "quantile_levels must contain finite values in [0, 1]",
        )
    if any(left >= right for left, right in zip(levels, levels[1:], strict=False)):
        raise FoundationProviderError(
            "INVALID_REQUEST",
            "quantile_levels must be strictly increasing",
        )
    return levels


def _normalize_num_samples(value: Any) -> int:
    if isinstance(value, bool):
        raise FoundationProviderError("INVALID_REQUEST", "num_samples must be an integer")
    try:
        num_samples = int(value)
    except (TypeError, ValueError) as exc:
        raise FoundationProviderError(
            "INVALID_REQUEST",
            "num_samples must be an integer",
        ) from exc
    if not 1 <= num_samples <= 100:
        raise FoundationProviderError(
            "INVALID_REQUEST",
            "num_samples must be in the inclusive range 1..100",
        )
    return num_samples


def validate_sundial_distribution_response(
    response: dict[str, Any],
    *,
    expected_series_count: int,
    expected_num_samples: int,
    expected_horizon: int,
    quantile_levels: tuple[float, ...],
    point_strategy: str,
    requested_device: str,
) -> np.ndarray:
    if response.get("status") != "OK":
        raise FoundationProviderError(
            str(response.get("status", "PREDICT_FAILED")),
            str(response.get("message", "Sundial provider failed")),
        )
    if int(response.get("schema_version", 0)) != 1:
        raise FoundationProviderError("INVALID_RESPONSE", "schema_version must be 1")
    if int(response.get("provider_version", 0)) != 2:
        raise FoundationProviderError("INVALID_RESPONSE", "provider_version must be 2")

    expected_sample_shape = (
        expected_series_count,
        expected_num_samples,
        expected_horizon,
    )
    samples = np.asarray(response.get("samples"), dtype=float)
    if samples.shape != expected_sample_shape:
        raise FoundationProviderError(
            "INVALID_PREDICTION",
            f"sample shape mismatch: expected={expected_sample_shape}, actual={samples.shape}",
        )
    if list(samples.shape) != response.get("samples_shape"):
        raise FoundationProviderError(
            "INVALID_PREDICTION",
            "samples_shape does not match samples",
        )
    if not np.isfinite(samples).all():
        raise FoundationProviderError(
            "INVALID_PREDICTION",
            "samples contain NaN or Inf",
        )

    expected_matrix_shape = (expected_series_count, expected_horizon)
    statistics = response.get("sample_statistics")
    if not isinstance(statistics, dict):
        raise FoundationProviderError("INVALID_RESPONSE", "sample_statistics is required")
    statistic_arrays: dict[str, np.ndarray] = {}
    for name in ("mean", "median", "std"):
        value = np.asarray(statistics.get(name), dtype=float)
        if value.shape != expected_matrix_shape or not np.isfinite(value).all():
            raise FoundationProviderError(
                "INVALID_PREDICTION",
                f"sample statistic {name} has an invalid shape or value",
            )
        statistic_arrays[name] = value
    if np.any(statistic_arrays["std"] < 0.0):
        raise FoundationProviderError(
            "INVALID_PREDICTION",
            "sample standard deviation must be non-negative",
        )

    quantiles = response.get("quantiles")
    if not isinstance(quantiles, dict):
        raise FoundationProviderError("INVALID_RESPONSE", "quantiles are required")
    expected_keys = [_quantile_key(level) for level in quantile_levels]
    if list(quantiles) != expected_keys:
        raise FoundationProviderError(
            "INVALID_PREDICTION",
            f"quantile keys mismatch: expected={expected_keys}, actual={list(quantiles)}",
        )
    quantile_arrays: list[np.ndarray] = []
    for key in expected_keys:
        value = np.asarray(quantiles[key], dtype=float)
        if value.shape != expected_matrix_shape or not np.isfinite(value).all():
            raise FoundationProviderError(
                "INVALID_PREDICTION",
                f"quantile {key} has an invalid shape or value",
            )
        quantile_arrays.append(value)
    stacked_quantiles = np.stack(quantile_arrays, axis=0)
    if np.any(np.diff(stacked_quantiles, axis=0) < 0.0):
        raise FoundationProviderError(
            "INVALID_PREDICTION",
            "empirical quantiles cross",
        )
    if response.get("quantile_source") != "EMPIRICAL_FROM_GENERATED_SAMPLES":
        raise FoundationProviderError(
            "INVALID_RESPONSE",
            "quantile_source must identify empirical generated-sample quantiles",
        )
    if tuple(float(item) for item in response.get("quantile_levels", [])) != quantile_levels:
        raise FoundationProviderError(
            "INVALID_RESPONSE",
            "quantile_levels do not match the request",
        )

    if point_strategy not in {"mean", "median"}:
        raise FoundationProviderError("INVALID_REQUEST", "invalid point_strategy")
    predictions = np.asarray(response.get("predictions"), dtype=float)
    expected_prediction_shape = (expected_series_count,)
    if predictions.shape != expected_prediction_shape or not np.isfinite(predictions).all():
        raise FoundationProviderError(
            "INVALID_PREDICTION",
            "legacy point predictions have an invalid shape or value",
        )
    selected = statistic_arrays[point_strategy][:, 0]
    if not np.allclose(predictions, selected, rtol=0.0, atol=1e-12):
        raise FoundationProviderError(
            "INVALID_PREDICTION",
            "legacy predictions do not match the selected point strategy",
        )

    properties = response.get("properties")
    if not isinstance(properties, dict):
        raise FoundationProviderError("PROPERTY_INSPECTION_FAILED", "properties are required")
    if properties.get("loaded_from_resolved_snapshot") is not True:
        raise FoundationProviderError(
            "ARTIFACT_MISSING",
            "provider did not prove direct loading from the resolved snapshot",
        )
    if properties.get("offline_mode") is not True:
        raise FoundationProviderError(
            "PROPERTY_INSPECTION_FAILED",
            "provider did not prove offline mode",
        )
    if not properties.get("remote_code_sha256"):
        raise FoundationProviderError(
            "ARTIFACT_MISSING",
            "remote_code_sha256 is required",
        )

    gpu = response.get("gpu_evidence")
    if not isinstance(gpu, dict):
        raise FoundationProviderError("GPU_PARTIAL", "gpu_evidence is required")
    if gpu.get("cpu_fallback") is not False:
        raise FoundationProviderError("CPU_FALLBACK_FORBIDDEN", "CPU fallback is forbidden")
    if requested_device == "cuda":
        if gpu.get("execution_device") != "cuda" or gpu.get("gpu_used") is not True:
            raise FoundationProviderError(
                "CPU_FALLBACK_FORBIDDEN",
                "CUDA request did not execute on CUDA",
            )
    return predictions


class SundialProvider(FoundationProvider):
    repo_id = "thuml/sundial-base-128m"
    revision = "3212e42564493f520593e5414af4367fc4b49226"

    def validate_environment(self) -> dict[str, Any]:
        if not SUNDIAL_ENV.exists():
            raise FoundationProviderError(
                "DEPENDENCY_MISSING",
                f"missing Sundial environment: {SUNDIAL_ENV}",
            )
        if not (SUNDIAL_ENV / "uv.lock").exists():
            raise FoundationProviderError(
                "DEPENDENCY_MISSING",
                f"missing Sundial lockfile: {SUNDIAL_ENV / 'uv.lock'}",
            )
        if not SUNDIAL_RUNNER.exists():
            raise FoundationProviderError(
                "PROVIDER_NOT_IMPLEMENTED",
                f"missing Sundial runner: {SUNDIAL_RUNNER}",
            )
        _load_remote_code_allowlist(SUNDIAL_REMOTE_CODE_REVIEW)
        return {
            "environment": str(SUNDIAL_ENV),
            "runner": str(SUNDIAL_RUNNER),
            "repo_id": self.repo_id,
            "revision": self.revision,
            "subprocess_contract": "json-file-v1-sundial-distribution-v2",
            "remote_code_review": str(SUNDIAL_REMOTE_CODE_REVIEW),
        }

    def load(self) -> SundialProvider:
        self.validate_environment()
        return self

    def _effective_request_options(
        self,
    ) -> tuple[int, tuple[float, ...], bool, str]:
        if not self.precision.startswith("32"):
            raise FoundationProviderError(
                "UNSUPPORTED_PRECISION",
                f"Sundial provider v2 supports only FP32, got {self.precision}",
            )
        num_samples = _normalize_num_samples(self.params.get("num_samples", 3))
        quantile_levels = _normalize_quantile_levels(self.params.get("quantile_levels"))
        revin = self.params.get("revin", True)
        if not isinstance(revin, bool):
            raise FoundationProviderError("INVALID_REQUEST", "revin must be a boolean")
        point_strategy = str(self.params.get("point_strategy", "median"))
        if point_strategy not in {"mean", "median"}:
            raise FoundationProviderError(
                "INVALID_REQUEST",
                "point_strategy must be 'mean' or 'median'",
            )
        return num_samples, quantile_levels, revin, point_strategy

    def _run_provider(self, history: pd.DataFrame) -> dict[str, Any]:
        self.validate_environment()
        num_samples, quantile_levels, revin, point_strategy = (
            self._effective_request_options()
        )
        request = {
            "schema_version": 1,
            "model_id": self.spec.model_id,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "local_files_only": True,
            "device": self.device,
            "dtype": "float32",
            "history": history[[f"n{i}" for i in range(1, 8)]].to_dict(orient="records"),
            "prediction_length": 1,
            "num_samples": num_samples,
            "quantile_levels": list(quantile_levels),
            "point_strategy": point_strategy,
            "revin": revin,
            "seed": self.seed,
            "approved_remote_code_sha256": _load_remote_code_allowlist(
                SUNDIAL_REMOTE_CODE_REVIEW
            ),
        }
        validate_provider_request(request)
        with tempfile.TemporaryDirectory(prefix="loto-sundial-") as tmp:
            request_path = Path(tmp) / "provider_request.json"
            response_path = Path(tmp) / "provider_response.json"
            request_path.write_text(
                json.dumps(request, ensure_ascii=False),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"
            if self.device == "cpu":
                env["CUDA_VISIBLE_DEVICES"] = ""
            proc = subprocess.run(
                [
                    "uv",
                    "run",
                    "--project",
                    str(SUNDIAL_ENV),
                    "python",
                    str(SUNDIAL_RUNNER),
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=int(self.params.get("provider_timeout", 900)),
                check=False,
            )
            if proc.returncode != 0:
                raise FoundationProviderError(
                    "PREDICT_FAILED",
                    "Sundial subprocess failed "
                    f"rc={proc.returncode}: {proc.stderr[-2000:] or proc.stdout[-2000:]}",
                )
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise FoundationProviderError(
                    "PREDICT_FAILED",
                    f"Sundial provider returned invalid JSON: {exc}",
                ) from exc
        if response.get("status") != "OK":
            raise FoundationProviderError(
                str(response.get("status", "PREDICT_FAILED")),
                str(response.get("message", "Sundial provider failed")),
            )
        try:
            validate_provider_response(response, expected_shape=(7,))
        except SubprocessProviderContractError as exc:
            raise FoundationProviderError(exc.status, str(exc)) from exc
        validate_sundial_distribution_response(
            response,
            expected_series_count=7,
            expected_num_samples=num_samples,
            expected_horizon=1,
            quantile_levels=quantile_levels,
            point_strategy=point_strategy,
            requested_device=self.device,
        )
        self.last_response = response
        self.resolved = dict(response.get("artifact_reference", {}))
        return response

    def predict_distribution(self, history: pd.DataFrame) -> dict[str, Any]:
        return self._run_provider(history)

    def predict(self, history: pd.DataFrame) -> np.ndarray:
        response = self.predict_distribution(history)
        return np.asarray(response["predictions"], dtype=float).reshape(7)

    def save(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        payload = self.inspect_properties()
        if hasattr(self, "last_response"):
            payload["artifact_reference"] = self.last_response.get("artifact_reference", {})
            payload["provider_properties"] = self.last_response.get("properties", {})
            payload["gpu_evidence"] = self.last_response.get("gpu_evidence", {})
            payload["distribution_contract"] = {
                "provider_version": self.last_response.get("provider_version"),
                "samples_shape": self.last_response.get("samples_shape"),
                "quantile_levels": self.last_response.get("quantile_levels"),
                "quantile_source": self.last_response.get("quantile_source"),
                "point_strategy": self.last_response.get("point_strategy"),
            }
        (path / "provider.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def load_saved(self, path: Path) -> SundialProvider:
        if not (path / "provider.json").exists():
            raise FoundationProviderError(
                "ARTIFACT_MISSING",
                f"provider artifact missing: {path / 'provider.json'}",
            )
        self.saved_reference = json.loads(
            (path / "provider.json").read_text(encoding="utf-8")
        )
        return self.load()

    def inspect_properties(self) -> dict[str, Any]:
        data = super().inspect_properties()
        data.update(
            {
                "repo_id": self.repo_id,
                "revision": self.revision,
                "zero_shot": True,
                "probabilistic_samples": True,
                "empirical_quantiles": True,
                "supports_batched_univariate": True,
                "supports_joint_multivariate": False,
                "environment": str(SUNDIAL_ENV),
                "subprocess_provider": True,
                "provider_contract_version": 2,
                **getattr(self, "resolved", {}),
            }
        )
        if hasattr(self, "last_response"):
            data.update(self.last_response.get("properties", {}))
        return data
