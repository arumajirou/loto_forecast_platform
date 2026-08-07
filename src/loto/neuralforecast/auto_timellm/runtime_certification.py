"""AutoTimeLLM adapter for the provider-neutral runtime-certification SDK."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from .contracts import MODEL_ID, PinnedLLMIdentity
from .runtime_contracts import (
    AutoTimeLLMRuntimeRequest,
    canonical_request_payload,
    canonical_request_sha256,
    load_worker_response,
)


class RuntimeSDKUnavailableError(RuntimeError):
    pass


class AutoTimeLLMCertificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeSDK:
    root: ModuleType
    contracts: ModuleType
    statuses: ModuleType
    verifier: ModuleType
    runner: ModuleType
    artifacts: ModuleType


def load_runtime_sdk() -> RuntimeSDK:
    try:
        root = importlib.import_module("loto.runtime_certification")
        contracts = importlib.import_module("loto.runtime_certification.contracts")
        statuses = importlib.import_module("loto.runtime_certification.statuses")
        verifier = importlib.import_module("loto.runtime_certification.verifier")
        runner = importlib.import_module("loto.runtime_certification.subprocess_runner")
        artifacts = importlib.import_module("loto.runtime_certification.artifacts")
    except ModuleNotFoundError as exc:
        raise RuntimeSDKUnavailableError(
            "AutoTimeLLM runtime certification requires the provider-neutral SDK from PR #123"
        ) from exc
    return RuntimeSDK(
        root=root,
        contracts=contracts,
        statuses=statuses,
        verifier=verifier,
        runner=runner,
        artifacts=artifacts,
    )


def _artifact_role(path: str) -> str:
    filename = Path(path).name
    if path == "config.json":
        return "model_config"
    if path.endswith((".safetensors", ".bin")):
        return "model_weight"
    if filename.startswith("tokenizer") or filename in {
        "vocab.json",
        "merges.txt",
        "tokenizer.model",
        "spiece.model",
    }:
        return "tokenizer"
    return "snapshot_support"


def _combined_weight_sha256(identity: PinnedLLMIdentity) -> str | None:
    rows = [
        {
            "relative_path": item.relative_path,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
        }
        for item in identity.files
        if item.relative_path.endswith((".safetensors", ".bin"))
    ]
    if not rows:
        return None
    encoded = json.dumps(
        sorted(rows, key=lambda item: item["relative_path"]),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_common_identities(
    request: AutoTimeLLMRuntimeRequest,
    *,
    sdk: RuntimeSDK,
) -> dict[str, Any]:
    artifact_cls = sdk.contracts.ArtifactIdentity
    snapshot_artifacts = [
        artifact_cls(
            relative_path=item.relative_path,
            sha256=item.sha256,
            size_bytes=item.size_bytes,
            role=_artifact_role(item.relative_path),
        )
        for item in request.llm_identity.files
    ]
    config_sha256 = next(
        item.sha256
        for item in request.llm_identity.files
        if item.relative_path == "config.json"
    )
    request_identity = sdk.root.RequestIdentity(
        request_id=request.run_id,
        request_sha256=canonical_request_sha256(request),
        seed=request.seed,
        requested_device=request.requested_device,
        input_schema_id="auto-timellm-runtime-request-v1",
    )
    package_identity = sdk.root.PackageIdentity(
        distribution="neuralforecast",
        version=request.expected_neuralforecast_version,
        artifact_sha256=None,
        source_revision=None,
    )
    model_identity = sdk.root.ModelIdentity(
        model_id=MODEL_ID,
        repository_id=request.llm_identity.repo_id,
        revision=request.llm_identity.revision,
        config_sha256=config_sha256,
        weight_sha256=_combined_weight_sha256(request.llm_identity),
    )
    snapshot_identity = sdk.root.SnapshotIdentity(
        snapshot_root=request.llm_identity.snapshot_path,
        expected_revision=request.llm_identity.revision,
        artifacts=snapshot_artifacts,
    )
    output_contract = sdk.root.OutputContract(
        expected_shape=[1, request.horizon],
        quantile_axis=None,
        quantile_levels=[],
        monotonic_tolerance=0.0,
    )
    return {
        "request": request_identity,
        "package": package_identity,
        "model": model_identity,
        "snapshot": snapshot_identity,
        "output_contract": output_contract,
    }


def _worker_output_path(output_root: Path, run_label: str) -> Path:
    return output_root / "processes" / run_label / "WORKER_RESPONSE.json"


def build_command_specs(
    request: AutoTimeLLMRuntimeRequest,
    *,
    request_path: Path,
    output_root: Path,
    sdk: RuntimeSDK,
    python_executable: str | None = None,
) -> tuple[Any, Any]:
    executable = python_executable or sys.executable
    environment = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONHASHSEED": str(request.seed),
    }
    commands = []
    for run_label in ("run-a", "run-b"):
        output_path = _worker_output_path(output_root, run_label)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        commands.append(
            sdk.root.CommandSpec(
                argv=[
                    executable,
                    "-m",
                    "loto.neuralforecast.auto_timellm.runtime_worker",
                    "--request",
                    str(request_path),
                    "--output",
                    str(output_path),
                    "--run-label",
                    run_label,
                ],
                cwd=request.working_directory,
                timeout_seconds=request.timeout_seconds,
                environment=environment,
            )
        )
    return commands[0], commands[1]


def _gpu_pid_absent(provider_pid: int) -> bool:
    command = [
        "nvidia-smi",
        "--query-compute-apps=pid",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    active_pids = {
        int(line.strip())
        for line in completed.stdout.splitlines()
        if line.strip().isdigit()
    }
    return provider_pid not in active_pids


def build_observation_loader(
    output_root: Path,
    *,
    sdk: RuntimeSDK,
    pid_release_checker: Callable[[int], bool] = _gpu_pid_absent,
) -> Callable[[str, Any], Any]:
    def load(run_label: str, execution: Any) -> Any:
        response_path = _worker_output_path(output_root, run_label)
        if not response_path.is_file():
            raise AutoTimeLLMCertificationError(
                f"worker response is missing for {run_label}: {response_path}"
            )
        response = load_worker_response(response_path)
        if response.run_label != run_label:
            raise AutoTimeLLMCertificationError("worker response run_label mismatch")
        if response.status != "PASS":
            raise AutoTimeLLMCertificationError(
                f"worker failed: {response.error_type}: {response.error_message}"
            )
        if response.package_version is None or response.output is None:
            raise AutoTimeLLMCertificationError("worker PASS response is incomplete")
        if response.effective_device is None or response.cpu_fallback is None:
            raise AutoTimeLLMCertificationError("worker device response is incomplete")
        if response.peak_vram_bytes is None:
            raise AutoTimeLLMCertificationError("worker VRAM response is incomplete")

        samples = [
            sdk.contracts.GPUProcessSample(
                provider_pid=item.provider_pid,
                gpu_uuid=item.gpu_uuid,
                used_memory_bytes=item.used_memory_bytes,
                observed_at_utc=item.observed_at_utc,
            )
            for item in response.external_gpu_samples
        ]
        pid_released = (
            True
            if response.requested_device == "cpu"
            else pid_release_checker(response.provider_pid)
        )
        device = sdk.root.DeviceEvidence(
            requested_device=response.requested_device,
            effective_device=response.effective_device,
            cpu_fallback=response.cpu_fallback,
            provider_pid=response.provider_pid,
            provider_gpu_pid=response.provider_gpu_pid,
            gpu_uuid=response.gpu_uuid,
            peak_vram_bytes=response.peak_vram_bytes,
            external_gpu_samples=samples,
            pid_released_after_exit=pid_released,
            origin=sdk.statuses.EvidenceOrigin.REAL,
        )
        return sdk.root.RunObservation(
            execution=execution,
            output=[list(row) for row in response.output],
            device=device,
            load_success=response.load_success,
            input_validation_success=response.input_validation_success,
            inference_success=response.inference_success,
            save_succeeded=response.save_succeeded,
            reload_succeeded=response.reload_succeeded,
            re_predict_succeeded=response.re_predict_succeeded,
        )

    return load


def _prepare_output_root(output_root: Path) -> Path:
    if output_root.exists() and any(output_root.iterdir()):
        raise AutoTimeLLMCertificationError(
            "output_root must not be an existing non-empty directory"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    if output_root.is_symlink():
        raise AutoTimeLLMCertificationError("output_root must not be a symlink")
    return output_root.resolve(strict=True)


def _atomic_write_request(path: Path, request: AutoTimeLLMRuntimeRequest) -> None:
    content = json.dumps(
        canonical_request_payload(request),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def certify_auto_timellm(
    request: AutoTimeLLMRuntimeRequest,
    output_root: Path,
    *,
    sdk: RuntimeSDK | None = None,
    executor: Any | None = None,
    package_version_reader: Callable[[str], str] | None = None,
    pid_release_checker: Callable[[int], bool] = _gpu_pid_absent,
) -> Any:
    resolved_sdk = sdk or load_runtime_sdk()
    evidence_root = _prepare_output_root(output_root)
    request_path = evidence_root / "RUNTIME_REQUEST.json"
    _atomic_write_request(request_path, request)
    identities = build_common_identities(request, sdk=resolved_sdk)
    first_command, second_command = build_command_specs(
        request,
        request_path=request_path,
        output_root=evidence_root,
        sdk=resolved_sdk,
    )
    profile = (
        resolved_sdk.statuses.CertificationProfile.CPU_SMOKE
        if request.profile == "CPU_SMOKE"
        else resolved_sdk.statuses.CertificationProfile.GPU_FORMAL
    )
    real_executor = executor or resolved_sdk.runner.SubprocessExecutor()
    try:
        report = resolved_sdk.root.execute_two_process_certification(
            certification_id=f"auto-timellm-{request.run_id}",
            profile=profile,
            evidence_origin=resolved_sdk.statuses.EvidenceOrigin.REAL,
            request=identities["request"],
            package=identities["package"],
            model=identities["model"],
            snapshot=identities["snapshot"],
            output_contract=identities["output_contract"],
            request_payload=canonical_request_payload(request),
            first_command=first_command,
            second_command=second_command,
            executor=real_executor,
            observation_loader=build_observation_loader(
                evidence_root,
                sdk=resolved_sdk,
                pid_release_checker=pid_release_checker,
            ),
            package_version_reader=package_version_reader,
            replay_tolerance=request.replay_tolerance,
        )
    except Exception as exc:
        failure_path = evidence_root / "CERTIFICATION_FAILURE.json"
        resolved_sdk.artifacts.atomic_write_json(
            failure_path,
            {
                "schema_version": "1.0.0",
                "status": "BLOCKED",
                "run_id": request.run_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "runtime_certified": False,
                "accuracy_status": "NOT_EVALUATED",
            },
        )
        sha_path = evidence_root / "SHA256SUMS"
        resolved_sdk.artifacts.write_sha256s(evidence_root, sha_path)
        resolved_sdk.artifacts.verify_sha256s(evidence_root, sha_path)
        zip_path = evidence_root.with_name(f"{evidence_root.name}.zip")
        resolved_sdk.artifacts.create_evidence_zip(evidence_root, zip_path)
        raise AutoTimeLLMCertificationError(
            f"AutoTimeLLM runtime certification was blocked: {exc}"
        ) from exc

    report_path = evidence_root / "CERTIFICATION_REPORT.json"
    resolved_sdk.artifacts.atomic_write_json(report_path, report.model_dump(mode="json"))
    manifest = resolved_sdk.artifacts.build_artifact_manifest(
        evidence_root,
        excluded={"CERTIFICATION_REPORT.json", "SHA256SUMS"},
    )
    report = report.model_copy(update={"artifacts": manifest})
    resolved_sdk.artifacts.atomic_write_json(report_path, report.model_dump(mode="json"))
    sha_path = evidence_root / "SHA256SUMS"
    resolved_sdk.artifacts.write_sha256s(evidence_root, sha_path)
    resolved_sdk.artifacts.verify_sha256s(evidence_root, sha_path)
    zip_path = evidence_root.with_name(f"{evidence_root.name}.zip")
    resolved_sdk.artifacts.create_evidence_zip(evidence_root, zip_path)
    return report


__all__ = [
    "AutoTimeLLMCertificationError",
    "RuntimeSDK",
    "RuntimeSDKUnavailableError",
    "build_command_specs",
    "build_common_identities",
    "build_observation_loader",
    "certify_auto_timellm",
    "load_runtime_sdk",
]
