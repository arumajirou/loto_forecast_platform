"""Fail-closed Forecast MCP service backed by the GPU Exclusive Supervisor."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from pydantic import ValidationError

from loto.adapters.moirai2.contracts import (
    Moirai2ProviderRequest,
    Moirai2ProviderResponse,
    Operation,
)
from loto.gpu_exclusive.adapters import HttpRuntime, NvidiaSmiProbe
from loto.gpu_exclusive.models import ForecastJobConfig, SupervisorConfig
from loto.gpu_exclusive.supervisor import ExclusiveGpuSupervisor

from .contracts import (
    DevelopmentRequestManifest,
    ForecastMcpConfig,
    ForecastToolRequest,
    MOIRAI2_REPO_ID,
    MOIRAI2_REVISION,
)


class SupervisorLike(Protocol):
    def run(self) -> dict[str, Any]: ...


SupervisorFactory = Callable[[SupervisorConfig], SupervisorLike]


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical_json_bytes(payload))
    temporary.replace(path)


def load_config(path: Path) -> ForecastMcpConfig:
    return ForecastMcpConfig.model_validate_json(path.read_text(encoding="utf-8"))


class ForecastMcpService:
    """Runs exactly one operator-approved Moirai-2 Numbers3 CUDA route."""

    def __init__(
        self,
        config: ForecastMcpConfig,
        *,
        supervisor_factory: SupervisorFactory = ExclusiveGpuSupervisor,
    ) -> None:
        self.config = config
        self._supervisor_factory = supervisor_factory

    def _load_approved_request(self) -> Moirai2ProviderRequest:
        manifest = DevelopmentRequestManifest.model_validate_json(
            self.config.route.request_manifest.read_text(encoding="utf-8")
        )
        actual_sha = _sha256_file(self.config.route.approved_request)
        if actual_sha != manifest.request_sha256:
            raise RuntimeError(
                "approved development request SHA-256 mismatch: "
                f"expected={manifest.request_sha256}, actual={actual_sha}"
            )
        request = Moirai2ProviderRequest.model_validate_json(
            self.config.route.approved_request.read_text(encoding="utf-8")
        )
        self._validate_route(request)
        return request

    @staticmethod
    def _validate_route(request: Moirai2ProviderRequest) -> None:
        expected_geometry = {
            "game_id": "numbers3",
            "position_count": 3,
            "candidate_min": 0,
            "candidate_max": 9,
            "strictly_increasing": False,
        }
        if request.operation is not Operation.PREDICT:
            raise RuntimeError("approved request must use operation=predict")
        if request.repo_id != MOIRAI2_REPO_ID or request.revision != MOIRAI2_REVISION:
            raise RuntimeError("approved request is not the pinned Moirai-2 identity")
        if request.game_geometry.model_dump(mode="json") != expected_geometry:
            raise RuntimeError("approved request is not exact Numbers3 geometry")
        if request.series_layout != "position_multivariate":
            raise RuntimeError("approved request must use position_multivariate layout")
        if request.position_columns != ["n1", "n2", "n3"]:
            raise RuntimeError("approved request must use exact Numbers3 position columns")
        if request.prediction_length != 1:
            raise RuntimeError("approved request must use prediction_length=1")
        if request.device != "cuda":
            raise RuntimeError("approved request must require CUDA")
        if request.local_files_only is not True:
            raise RuntimeError("approved request must be local-files-only")

    @staticmethod
    def _validate_provider_response(response: Moirai2ProviderResponse) -> None:
        if response.status != "OK" or response.phase != "predict":
            raise RuntimeError(
                f"Moirai-2 provider did not succeed: {response.status}/{response.phase}: "
                f"{response.message}"
            )
        if response.model_identity.get("repo_id") != MOIRAI2_REPO_ID:
            raise RuntimeError("provider response repo identity mismatch")
        if response.model_identity.get("revision") != MOIRAI2_REVISION:
            raise RuntimeError("provider response revision mismatch")
        if response.series_identity != ["n1", "n2", "n3"]:
            raise RuntimeError("provider response series identity mismatch")
        if response.prediction_index != [1]:
            raise RuntimeError("provider response prediction index mismatch")
        if len(response.point_forecast) != 1 or len(response.point_forecast[0]) != 3:
            raise RuntimeError("provider response point forecast must have shape [1, 3]")
        if not all(math.isfinite(float(value)) for value in response.point_forecast[0]):
            raise RuntimeError("provider point forecast contains non-finite values")
        runtime = response.runtime_evidence
        gpu = response.gpu_evidence
        if runtime is None or gpu is None:
            raise RuntimeError("provider runtime/GPU evidence is missing")
        if runtime.output_shape != [1, 3]:
            raise RuntimeError("provider output_shape evidence mismatch")
        if runtime.execution_device != "cuda" or runtime.cpu_fallback:
            raise RuntimeError("provider runtime evidence indicates CUDA mismatch/fallback")
        if gpu.execution_device != "cuda" or gpu.cpu_fallback:
            raise RuntimeError("provider GPU evidence indicates CUDA mismatch/fallback")
        if gpu.provider_pid <= 0 or gpu.gpu_pid != gpu.provider_pid:
            raise RuntimeError("provider GPU PID evidence is invalid")
        if gpu.peak_vram_bytes <= 0:
            raise RuntimeError("provider peak VRAM evidence is missing")

    def status(self) -> dict[str, Any]:
        route_error: str | None = None
        try:
            self._load_approved_request()
        except (OSError, RuntimeError, ValidationError) as exc:
            route_error = f"{type(exc).__name__}: {exc}"

        qwen_running = HttpRuntime(self.config.qwen).running()
        gpu_snapshot: dict[str, int] | None = None
        gpu_error: str | None = None
        try:
            snapshot = NvidiaSmiProbe(self.config.gpu).snapshot()
            gpu_snapshot = {
                "index": snapshot.index,
                "memory_used_mib": snapshot.memory_used_mib,
                "memory_total_mib": snapshot.memory_total_mib,
            }
        except Exception as exc:  # live status must report rather than mutate
            gpu_error = f"{type(exc).__name__}: {exc}"

        return {
            "status": "READY" if route_error is None else "BLOCKED",
            "endpoint": f"http://{self.config.server.host}:{self.config.server.port}/mcp",
            "route": {
                "game": "numbers3",
                "model": "moirai2",
                "horizon": 1,
                "device": "cuda",
                "scope": "development",
                "repo_id": MOIRAI2_REPO_ID,
                "revision": MOIRAI2_REVISION,
            },
            "route_error": route_error,
            "qwen_running": qwen_running,
            "gate_configured": True,
            "gpu": gpu_snapshot,
            "gpu_error": gpu_error,
            "holdout_access": False,
            "prospective_access": False,
            "actual_access": False,
        }

    def forecast(self, tool_request: ForecastToolRequest) -> dict[str, Any]:
        ForecastToolRequest.model_validate(tool_request.model_dump(mode="json"))
        approved = self._load_approved_request()

        run_id = (
            "forecast-mcp-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12]
        )
        run_dir = self.config.server.artifact_root / run_id
        if run_dir.exists():
            raise RuntimeError(f"refusing to reuse existing run directory: {run_dir}")
        run_dir.mkdir(parents=True)

        request_path = run_dir / "provider_request.json"
        response_path = run_dir / "provider_response.json"
        request = approved.model_copy(update={"run_id": run_id})
        _write_json(request_path, request.model_dump(mode="json"))

        command = [
            str(self.config.route.provider_python),
            str(self.config.route.provider_script),
            "--request",
            str(request_path),
            "--response",
            str(response_path),
            "--runtime-lane",
            self.config.route.runtime_lane,
        ]
        supervisor_config = SupervisorConfig(
            qwen=self.config.qwen,
            gpu=self.config.gpu,
            gate=self.config.gate,
            forecast=ForecastJobConfig(
                command=command,
                cwd=self.config.route.repo_root,
                env={"PYTHONUNBUFFERED": "1"},
                timeout_seconds=self.config.route.timeout_seconds,
            ),
            output_dir=run_dir / "supervisor",
            lock_path=self.config.lock_path,
            restore_qwen_if_initially_running=True,
            monitor_qwen_during_forecast=True,
        )
        supervisor_result = self._supervisor_factory(supervisor_config).run()
        _write_json(run_dir / "supervisor_result.json", supervisor_result)

        provider_payload: dict[str, Any] | None = None
        provider_error: str | None = None
        if response_path.is_file():
            try:
                provider_payload = json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                provider_error = f"invalid provider response JSON: {exc}"

        if supervisor_result.get("status") != "PASS":
            raise RuntimeError(
                "GPU Exclusive Supervisor failed closed: "
                f"{supervisor_result.get('failure')}; provider_error={provider_error}"
            )
        if not supervisor_result.get("qwen_initially_running"):
            raise RuntimeError("formal MCP forecast requires the selected Qwen runtime to be live")
        if not supervisor_result.get("qwen_restored"):
            raise RuntimeError("selected Qwen runtime was not restored")
        if not supervisor_result.get("gate_reopened"):
            raise RuntimeError("request gate was not reopened")
        if provider_payload is None:
            raise RuntimeError(provider_error or "provider response file is missing")

        provider_response = Moirai2ProviderResponse.model_validate(provider_payload)
        self._validate_provider_response(provider_response)
        runtime_evidence = provider_response.runtime_evidence
        gpu_evidence = provider_response.gpu_evidence
        if runtime_evidence is None or gpu_evidence is None:
            raise RuntimeError("provider runtime/GPU evidence disappeared after validation")

        prediction_payload = {
            "series_identity": provider_response.series_identity,
            "prediction_index": provider_response.prediction_index,
            "point_forecast": provider_response.point_forecast,
            "point_method": provider_response.point_method,
        }
        prediction_sha256 = _sha256_bytes(_canonical_json_bytes(prediction_payload))
        result = {
            "status": "PASS",
            "run_id": run_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "route": tool_request.model_dump(mode="json"),
            "model_identity": {
                "repo_id": MOIRAI2_REPO_ID,
                "revision": MOIRAI2_REVISION,
            },
            "prediction": prediction_payload,
            "prediction_sha256": prediction_sha256,
            "runtime_evidence": runtime_evidence.model_dump(mode="json"),
            "gpu_evidence": gpu_evidence.model_dump(mode="json"),
            "supervisor": {
                "qwen_initially_running": supervisor_result.get("qwen_initially_running"),
                "qwen_stopped": supervisor_result.get("qwen_stopped"),
                "qwen_restored": supervisor_result.get("qwen_restored"),
                "gate_reopened": supervisor_result.get("gate_reopened"),
                "forecast_exit_code": supervisor_result.get("forecast_exit_code"),
            },
            "holdout_access": False,
            "prospective_access": False,
            "actual_access": False,
            "evidence_boundary": (
                "provider-reported PID/VRAM is retained here; formal external GPU UUID/PID "
                "correlation remains a target-machine acceptance gate"
            ),
        }
        result_path = run_dir / "FORECAST_MCP_RESULT.json"
        _write_json(result_path, result)

        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "files": {
                "provider_request.json": _sha256_file(request_path),
                "provider_response.json": _sha256_file(response_path),
                "supervisor_result.json": _sha256_file(run_dir / "supervisor_result.json"),
                "FORECAST_MCP_RESULT.json": _sha256_file(result_path),
            },
        }
        manifest_path = run_dir / "ARTIFACT_MANIFEST.json"
        _write_json(manifest_path, manifest)

        checksum_rows: list[str] = []
        for path in sorted(
            candidate
            for candidate in run_dir.rglob("*")
            if candidate.is_file() and candidate.name != "SHA256SUMS"
        ):
            checksum_rows.append(f"{_sha256_file(path)}  {path.relative_to(run_dir).as_posix()}")
        (run_dir / "SHA256SUMS").write_text(
            "\n".join(checksum_rows) + "\n",
            encoding="utf-8",
        )
        return result
