from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from loto.adapters.gluonts.protocol import (
    GluonTSProviderRequest,
    GluonTSProviderResponse,
    ProviderStatus,
    protocol_schema_sha256,
)


@dataclass(frozen=True)
class ProviderInvocation:
    """Validated provider result and immutable artifact locations."""

    response: GluonTSProviderResponse
    run_dir: Path
    request_path: Path
    response_path: Path
    stdout_path: Path
    stderr_path: Path
    request_sha256: str
    response_sha256: str
    return_code: int


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Write bytes using fsync and atomic rename in the destination directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: Any) -> str:
    """Write canonical JSON atomically and return its SHA-256 digest."""

    content = _canonical_json_bytes(payload)
    atomic_write_bytes(path, content)
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one completed artifact without loading it fully into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _failed_response(request: GluonTSProviderRequest, error: str) -> GluonTSProviderResponse:
    return GluonTSProviderResponse(
        request_id=request.request_id,
        run_id=request.run_id,
        lane=request.lane,
        status=ProviderStatus.FAILED,
        errors=[error],
    )


def invoke_provider(
    request: GluonTSProviderRequest,
    command: Sequence[str],
    artifact_root: Path,
    timeout_seconds: float = 300.0,
) -> ProviderInvocation:
    """Invoke an isolated provider with immutable request, response, and log artifacts."""

    if not command:
        raise ValueError("provider command cannot be empty")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    run_dir = artifact_root / request.run_id / request.request_id
    request_path = run_dir / "request.json"
    response_path = run_dir / "response.json"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    request_sha256 = atomic_write_json(request_path, request.model_dump(mode="json"))

    completed: subprocess.CompletedProcess[str] | None = None
    try:
        environment = os.environ.copy()
        threads = str(request.resource_policy.threads_per_job)
        environment.update(
            {
                "MKL_NUM_THREADS": threads,
                "NUMEXPR_NUM_THREADS": threads,
                "OMP_NUM_THREADS": threads,
                "OPENBLAS_NUM_THREADS": threads,
                "PYTHONHASHSEED": str(request.seed),
            }
        )
        completed = subprocess.run(
            [*command, "--request", str(request_path), "--response", str(response_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=environment,
        )
        atomic_write_bytes(stdout_path, completed.stdout.encode("utf-8"))
        atomic_write_bytes(stderr_path, completed.stderr.encode("utf-8"))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        atomic_write_bytes(stdout_path, stdout.encode("utf-8"))
        atomic_write_bytes(stderr_path, stderr.encode("utf-8"))
        response = _failed_response(request, f"provider timeout after {timeout_seconds} seconds")
        response_sha256 = atomic_write_json(response_path, response.model_dump(mode="json"))
        return ProviderInvocation(
            response=response,
            run_dir=run_dir,
            request_path=request_path,
            response_path=response_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            request_sha256=request_sha256,
            response_sha256=response_sha256,
            return_code=124,
        )

    response_from_provider = response_path.exists()
    if response_from_provider:
        response = GluonTSProviderResponse.model_validate_json(response_path.read_text("utf-8"))
        response_sha256 = sha256_file(response_path)
    else:
        response = _failed_response(
            request,
            f"provider exited with code {completed.returncode} without response.json",
        )
        response_sha256 = atomic_write_json(response_path, response.model_dump(mode="json"))

    if response.request_id != request.request_id or response.run_id != request.run_id:
        response = _failed_response(request, "provider response identity mismatch")
        response_sha256 = atomic_write_json(response_path, response.model_dump(mode="json"))
    elif response.lane != request.lane:
        response = _failed_response(request, "provider response lane mismatch")
        response_sha256 = atomic_write_json(response_path, response.model_dump(mode="json"))
    elif response_from_provider:
        identity = response.metadata.get("provider_identity")
        provider_schema_sha = (
            identity.get("protocol_schema_sha256") if isinstance(identity, dict) else None
        )
        if provider_schema_sha != protocol_schema_sha256():
            response = _failed_response(request, "provider protocol schema hash mismatch")
            response_sha256 = atomic_write_json(response_path, response.model_dump(mode="json"))

    return ProviderInvocation(
        response=response,
        run_dir=run_dir,
        request_path=request_path,
        response_path=response_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        request_sha256=request_sha256,
        response_sha256=response_sha256,
        return_code=completed.returncode,
    )
