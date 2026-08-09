from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from loto.adapters.timer_base_84m.contracts import TimerRequest, TimerResponse
from loto.timer_base_84m_campaign.geometry import geometry_for
from loto.timer_base_84m_campaign.provenance import (
    CONFIG_SHA256,
    LICENSE,
    MODEL_ID,
    MODEL_REVISION,
    OBSERVED_SOURCE_HEAD,
    PYTHON_LANE,
    REPO_ID,
    SNAPSHOT_FILE_SHA256S,
    SOURCE_REPOSITORY,
    SOURCE_REVISION,
    TRANSFORMERS_VERSION,
    WEIGHT_SHA256,
    load_review,
    validate_remote_code_review,
)

DEPENDENCY_LOCK_SHA256 = "5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0"
TORCH_VERSION = "2.9.1+cu128"


class TimerProviderError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class TimerBase84MProvider:
    environment_dir: Path
    review_path: Path
    snapshot_dir: Path | None = None
    _model: Any = field(default=None, init=False, repr=False)
    _torch: Any = field(default=None, init=False, repr=False)
    _transformers: Any = field(default=None, init=False, repr=False)
    _loaded_snapshot: Path | None = field(default=None, init=False, repr=False)

    def identity(self) -> dict[str, Any]:
        return {
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "model_revision": MODEL_REVISION,
            "config_sha256": CONFIG_SHA256,
            "weight_sha256": WEIGHT_SHA256,
            "source_repository": SOURCE_REPOSITORY,
            "source_revision": SOURCE_REVISION,
            "observed_source_head": OBSERVED_SOURCE_HEAD,
            "transformers_version": TRANSFORMERS_VERSION,
            "torch_version": TORCH_VERSION,
            "python_lane": PYTHON_LANE,
            "license": LICENSE,
            "dependency_lock_sha256": DEPENDENCY_LOCK_SHA256,
            "runtime_status": "RUNTIME_CERTIFIED",
        }

    def validate_request(self, payload: dict[str, Any]) -> TimerRequest:
        return TimerRequest.model_validate(payload)

    def validate_request_json(self, payload: str | bytes | bytearray) -> TimerRequest:
        return TimerRequest.model_validate_json(payload)

    def validate_environment(self) -> dict[str, Any]:
        project_file = self.environment_dir / "pyproject.toml"
        if not project_file.is_file():
            raise TimerProviderError("DEPENDENCY_LOCK_INVALID", f"missing {project_file}")
        lock_file = self.environment_dir / "uv.lock"
        if not lock_file.is_file():
            raise TimerProviderError("DEPENDENCY_LOCK_INVALID", f"missing {lock_file}")
        lock_sha256 = hashlib.sha256(lock_file.read_bytes()).hexdigest()
        if lock_sha256 != DEPENDENCY_LOCK_SHA256:
            raise TimerProviderError(
                "DEPENDENCY_LOCK_INVALID",
                f"isolated uv.lock SHA-256 mismatch: {lock_sha256}",
            )
        return {
            "project_file": str(project_file),
            "lock_file": str(lock_file),
            "lock_sha256": lock_sha256,
        }

    def resolve_snapshot_manifest(self) -> dict[str, Any]:
        if not self.review_path.is_file():
            raise TimerProviderError("REMOTE_CODE_REVIEW_REQUIRED", "remote-code review is missing")
        try:
            review = load_review(self.review_path)
            validate_remote_code_review(review)
        except ValueError as exc:
            raise TimerProviderError("REMOTE_CODE_REVIEW_REQUIRED", str(exc)) from exc
        return review

    def inspect_properties(self) -> dict[str, Any]:
        return {
            **self.identity(),
            "point_forecast": True,
            "quantiles": False,
            "samples": False,
            "multivariate": False,
            "past_covariates": False,
            "known_future_covariates": False,
            "checkpoint_load": True,
            "predict": True,
            "retained_layouts": [
                "position_univariate",
                "position_panel_batched_univariate",
            ],
            "supported_horizons": [1, 2, 5],
            "cpu_fallback_allowed": False,
        }

    def _snapshot_path(self) -> Path:
        if self.snapshot_dir is not None:
            return self.snapshot_dir.expanduser().resolve()
        explicit = os.environ.get("LOTO_TIMER_BASE_84M_SNAPSHOT", "").strip()
        if explicit:
            return Path(explicit).expanduser().resolve()
        return (
            Path.home()
            / ".cache"
            / "loto"
            / "timer-base-84m"
            / "snapshots"
            / MODEL_REVISION
        ).resolve()

    def _verify_snapshot_bytes(self) -> Path:
        snapshot = self._snapshot_path()
        if not snapshot.is_dir():
            raise TimerProviderError("SNAPSHOT_HASH_MISMATCH", f"snapshot missing: {snapshot}")
        for name, expected in SNAPSHOT_FILE_SHA256S.items():
            path = snapshot / name
            if not path.is_file():
                raise TimerProviderError("SNAPSHOT_HASH_MISMATCH", f"snapshot file missing: {name}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise TimerProviderError(
                    "SNAPSHOT_HASH_MISMATCH",
                    f"snapshot SHA-256 mismatch for {name}: {actual}",
                )
        return snapshot

    @staticmethod
    def _require_certified_python_lane() -> None:
        if sys.version_info[:2] != (3, 10):
            raise TimerProviderError(
                "UNSUPPORTED_RUNTIME_LANE",
                f"Timer Base 84M requires Python 3.10; running {sys.version.split()[0]}",
            )

    @staticmethod
    def _hash_tensor_f32(tensor: Any) -> str:
        value = tensor.detach().to("cpu").contiguous().to(dtype=tensor.new_empty((), dtype=None).dtype)
        value = value.to(dtype=value.float().dtype)
        raw = value.numpy().astype("<f4", copy=False).tobytes()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _gpu_process_evidence(pid: int) -> tuple[str | None, int | None]:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
                    "--format=csv,noheader,nounits",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return None, None
        for line in result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 3 or parts[0] != str(pid):
                continue
            try:
                return parts[1], int(parts[2]) * 1024 * 1024
            except ValueError:
                return parts[1], None
        return None, None

    def load(self) -> dict[str, Any]:
        self.validate_environment()
        self.resolve_snapshot_manifest()
        snapshot = self._verify_snapshot_bytes()
        self._require_certified_python_lane()

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"

        import torch
        import transformers
        from transformers import AutoModelForCausalLM

        if transformers.__version__ != TRANSFORMERS_VERSION:
            raise TimerProviderError(
                "UNSUPPORTED_RUNTIME_LANE",
                f"transformers {transformers.__version__} != {TRANSFORMERS_VERSION}",
            )
        if torch.__version__ != TORCH_VERSION:
            raise TimerProviderError(
                "UNSUPPORTED_RUNTIME_LANE",
                f"torch {torch.__version__} != {TORCH_VERSION}",
            )

        model = AutoModelForCausalLM.from_pretrained(
            str(snapshot),
            trust_remote_code=True,
            local_files_only=True,
            torch_dtype=torch.float32,
        )
        model.eval()
        model.to("cpu")
        params = list(model.parameters())
        buffers = list(model.buffers())
        if not params:
            raise TimerProviderError("RUNTIME_NOT_CERTIFIED", "loaded model has no parameters")
        if not all(bool(torch.isfinite(value).all().item()) for value in params):
            raise TimerProviderError("RUNTIME_NOT_CERTIFIED", "non-finite model parameter detected")
        if not all(
            bool(torch.isfinite(value).all().item())
            for value in buffers
            if value.is_floating_point()
        ):
            raise TimerProviderError("RUNTIME_NOT_CERTIFIED", "non-finite model buffer detected")

        self._model = model
        self._torch = torch
        self._transformers = transformers
        self._loaded_snapshot = snapshot
        return {
            **self.identity(),
            "status": "LOADED",
            "model_class": model.__class__.__name__,
            "parameter_count": sum(value.numel() for value in params),
            "effective_device": str(params[0].device),
            "snapshot_path": str(snapshot),
            "runtime_pid": os.getpid(),
        }

    def _predict_layout(self, x: Any, *, layout: str, horizon: int) -> Any:
        assert self._model is not None
        if layout == "position_panel_batched_univariate":
            return self._model.generate(x, max_new_tokens=horizon)
        outputs = []
        for index in range(x.shape[0]):
            outputs.append(self._model.generate(x[index : index + 1], max_new_tokens=horizon))
        return self._torch.cat(outputs, dim=0)

    def predict(self, request: TimerRequest) -> TimerResponse:
        if self._model is None or self._torch is None:
            raise TimerProviderError("MODEL_NOT_LOADED", "call load() before predict()")
        if request.operation != "predict":
            raise TimerProviderError("RUNTIME_NOT_CERTIFIED", "predict() requires operation='predict'")

        torch = self._torch
        torch.manual_seed(request.seed)
        torch.set_grad_enabled(False)
        torch.use_deterministic_algorithms(True, warn_only=True)

        if request.requested_device == "cuda":
            if not torch.cuda.is_available():
                raise TimerProviderError("CUDA_UNAVAILABLE", "CUDA requested but unavailable")
            torch.cuda.set_device(0)
            torch.cuda.manual_seed_all(request.seed)
            target = torch.device("cuda:0")
        else:
            target = torch.device("cpu")

        self._model.to(target)
        x = torch.tensor(request.series, dtype=torch.float32, device=target)
        input_raw = x.detach().to("cpu").contiguous().numpy().astype("<f4", copy=False).tobytes()
        input_sha = hashlib.sha256(input_raw).hexdigest()

        with torch.inference_mode():
            y = self._predict_layout(
                x,
                layout=request.target_layout,
                horizon=request.prediction_length,
            )
        if request.requested_device == "cuda":
            torch.cuda.synchronize(0)

        geometry = geometry_for(request.game)
        expected_shape = (geometry.position_count, request.prediction_length)
        if tuple(y.shape) != expected_shape:
            raise TimerProviderError(
                "RUNTIME_NOT_CERTIFIED",
                f"output shape {tuple(y.shape)} != {expected_shape}",
            )
        if not bool(torch.isfinite(y).all().item()):
            raise TimerProviderError("RUNTIME_NOT_CERTIFIED", "non-finite prediction detected")
        if request.requested_device == "cuda" and not str(y.device).startswith("cuda"):
            raise TimerProviderError("RUNTIME_NOT_CERTIFIED", f"CUDA output is on {y.device}")
        if request.requested_device == "cpu" and str(y.device) != "cpu":
            raise TimerProviderError("RUNTIME_NOT_CERTIFIED", f"CPU output is on {y.device}")

        y_cpu = y.detach().to("cpu").contiguous().to(torch.float32)
        prediction_raw = y_cpu.numpy().astype("<f4", copy=False).tobytes()
        prediction_sha = hashlib.sha256(prediction_raw).hexdigest()
        predictions = tuple(tuple(float(value) for value in row) for row in y_cpu.tolist())
        runtime_pid = os.getpid()
        gpu_uuid: str | None = None
        gpu_vram: int | None = None
        effective_device: Literal["cpu", "cuda:0"]
        if request.requested_device == "cuda":
            effective_device = "cuda:0"
            gpu_uuid, gpu_vram = self._gpu_process_evidence(runtime_pid)
            if gpu_uuid is None or gpu_vram is None:
                raise TimerProviderError(
                    "RUNTIME_NOT_CERTIFIED",
                    "CUDA process was not visible in nvidia-smi during predict()",
                )
        else:
            effective_device = "cpu"

        return TimerResponse(
            schema_version="timer-base-84m.response.v1",
            run_id=request.run_id,
            status="PREDICTED",
            model_id=MODEL_ID,
            repo_id=REPO_ID,
            package_version=TRANSFORMERS_VERSION,
            source_revision=SOURCE_REVISION,
            observed_source_head=OBSERVED_SOURCE_HEAD,
            model_revision=MODEL_REVISION,
            config_sha256=CONFIG_SHA256,
            weight_sha256=WEIGHT_SHA256,
            license=LICENSE,
            game=request.game,
            target_layout=request.target_layout,
            context_length=request.context_length,
            prediction_length=request.prediction_length,
            seed=request.seed,
            requested_device=request.requested_device,
            effective_device=effective_device,
            cpu_fallback=False,
            input_shape=request.input_shape,
            output_shape=expected_shape,
            point_forecast=predictions,
            quantiles=None,
            samples=None,
            finite_check=True,
            chronology_evidence=request.chronology_evidence,
            actuals_used=False,
            runtime_pid=runtime_pid,
            gpu_uuid=gpu_uuid,
            gpu_process_vram_bytes=gpu_vram,
            input_series_sha256_f32=input_sha,
            prediction_sha256_f32=prediction_sha,
            chronology_mapping_sha256=request.chronology_evidence.mapping_sha256,
            artifact_paths=request.artifact_paths,
        )

    def close(self) -> None:
        model = self._model
        torch = self._torch
        self._model = None
        self._loaded_snapshot = None
        if model is not None:
            try:
                model.to("cpu")
            except Exception:
                pass
            del model
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
        self._torch = None
        self._transformers = None
