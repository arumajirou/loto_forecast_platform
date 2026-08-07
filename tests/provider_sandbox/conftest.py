from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.provider_sandbox import (  # noqa: E402
    BackendEvidence,
    EffectiveMountEvidence,
    EffectiveSandboxEvidence,
    MountKind,
    MountMode,
    ResourceLimits,
    SandboxBackend,
    SandboxExecutionRequest,
    SandboxMount,
    SandboxPolicy,
)
from loto.provider_sandbox.canonical import sha256_bytes  # noqa: E402

ZERO = "0" * 64
NOW = datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def sandbox_paths(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "runtime": tmp_path / "runtime",
        "repo": tmp_path / "repo",
        "model": tmp_path / "model",
        "input": tmp_path / "input.json",
        "output": tmp_path / "output",
    }
    paths["runtime"].mkdir()
    (paths["runtime"] / "bin").mkdir()
    (paths["runtime"] / "bin/python").write_text("fixture", encoding="utf-8")
    paths["repo"].mkdir()
    paths["model"].mkdir()
    paths["input"].write_text("{}", encoding="utf-8")
    paths["output"].mkdir()
    return paths


@pytest.fixture
def policy(sandbox_paths: dict[str, Path]) -> SandboxPolicy:
    mounts = (
        SandboxMount(
            mount_id="runtime",
            kind=MountKind.RUNTIME,
            mode=MountMode.READ_ONLY,
            source_path=str(sandbox_paths["runtime"]),
            target_path="/sandbox/runtime",
        ),
        SandboxMount(
            mount_id="repo",
            kind=MountKind.REPOSITORY,
            mode=MountMode.READ_ONLY,
            source_path=str(sandbox_paths["repo"]),
            target_path="/sandbox/repo",
        ),
        SandboxMount(
            mount_id="model",
            kind=MountKind.MODEL_SNAPSHOT,
            mode=MountMode.READ_ONLY,
            source_path=str(sandbox_paths["model"]),
            target_path="/sandbox/model",
        ),
        SandboxMount(
            mount_id="input",
            kind=MountKind.INPUT,
            mode=MountMode.READ_ONLY,
            source_path=str(sandbox_paths["input"]),
            target_path="/sandbox/input/request.json",
        ),
        SandboxMount(
            mount_id="output",
            kind=MountKind.OUTPUT,
            mode=MountMode.READ_WRITE_TMP,
            source_path=str(sandbox_paths["output"]),
            target_path="/sandbox/output",
        ),
        SandboxMount(
            mount_id="tmp",
            kind=MountKind.TMPFS,
            mode=MountMode.READ_WRITE_TMP,
            target_path="/sandbox/tmp",
        ),
    )
    return SandboxPolicy.create(
        policy_id="test-policy",
        backend=SandboxBackend.BUBBLEWRAP,
        untrusted_remote_code=True,
        mounts=mounts,
        environment_allowlist=("PYTHONDONTWRITEBYTECODE", "OMP_NUM_THREADS"),
        environment_deny_patterns=("CUSTOM_SECRET",),
        executable_allowlist=("/sandbox/runtime/bin/python",),
        gpu_device_allowlist=("GPU-TEST",),
        limits=ResourceLimits(
            pids=32,
            cpu_cores=2.0,
            memory_bytes=536870912,
            file_size_bytes=16777216,
            output_bytes=1048576,
            wall_timeout_seconds=60.0,
        ),
    )


@pytest.fixture
def execution_request() -> SandboxExecutionRequest:
    return SandboxExecutionRequest(
        request_id="request-1",
        run_id="run-1",
        executable="/sandbox/runtime/bin/python",
        arguments=("provider.py", "--mode", "smoke"),
        environment={"PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "2"},
        requested_gpu_devices=(),
        issued_at=NOW,
    )


@pytest.fixture
def backend() -> BackendEvidence:
    return BackendEvidence(
        backend=SandboxBackend.BUBBLEWRAP,
        available=True,
        executable_path="/usr/bin/bwrap",
        executable_sha256=ZERO,
        version="bubblewrap fixture",
        rootless=None,
        detected_at=NOW,
    )


@pytest.fixture
def effective(
    policy: SandboxPolicy,
    execution_request: SandboxExecutionRequest,
) -> EffectiveSandboxEvidence:
    mounts = tuple(
        EffectiveMountEvidence(
            mount_id=item.mount_id,
            kind=item.kind,
            mode=item.mode,
            target_path=item.target_path,
            source_path_sha256=(
                sha256_bytes(item.source_path.encode("utf-8"))
                if item.source_path is not None
                else None
            ),
        )
        for item in policy.mounts
    )
    return EffectiveSandboxEvidence.create(
        backend=policy.backend,
        network_disabled=True,
        root_read_only=True,
        no_new_privileges=True,
        all_capabilities_dropped=True,
        limits=policy.limits,
        mounts=mounts,
        environment_keys=tuple(sorted(execution_request.environment)),
        gpu_devices=execution_request.requested_gpu_devices,
        observed_at=NOW,
    )
