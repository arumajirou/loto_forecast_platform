from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .runtime_preflight import canonical_sha256, file_sha256

BootstrapStatus = Literal["PASS", "BLOCKED", "FAIL"]
StepStatus = Literal["PASS", "BLOCKED", "FAIL", "SKIPPED"]
Runner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], datetime]


class RuntimeBootstrapError(RuntimeError):
    """Base error for fail-closed runtime bootstrap failures."""


class RuntimeBootstrapProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    bootstrap_id: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    project_path: str
    runtime_profile_path: str
    lockfile_path: str
    python_version: str = Field(pattern=r"^\d+\.\d+$")
    preflight_output_path: str
    bootstrap_report_path: str
    approval_path: str
    timeout_seconds: int = Field(default=1800, ge=1, le=14400)
    uv_executable: str = "uv"
    allow_network_for_lock: bool = True
    require_frozen_sync: bool = True

    @model_validator(mode="after")
    def validate_paths(self) -> RuntimeBootstrapProfile:
        values = (
            self.project_path,
            self.runtime_profile_path,
            self.lockfile_path,
            self.preflight_output_path,
            self.bootstrap_report_path,
            self.approval_path,
        )
        for raw in values:
            path = Path(raw)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("all paths must be repository-relative")
        expected_lock = f"{self.project_path.rstrip('/')}/uv.lock"
        if self.lockfile_path != expected_lock:
            raise ValueError("lockfile_path must be the selected project uv.lock")
        outputs = {
            self.preflight_output_path,
            self.bootstrap_report_path,
            self.approval_path,
        }
        if len(outputs) != 3:
            raise ValueError("output paths must be distinct")
        if not self.require_frozen_sync:
            raise ValueError("runtime bootstrap requires frozen sync")
        return self


class BootstrapStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)
    status: StepStatus
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout_size_bytes: int = Field(default=0, ge=0)
    stderr_size_bytes: int = Field(default=0, ge=0)
    stdout_sha256: str | None = None
    stderr_sha256: str | None = None
    detail: str = ""


class RuntimeBootstrapReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    bootstrap_id: str
    profile_name: str
    overall_status: BootstrapStatus
    generated_at_utc: str
    process_id: int = Field(ge=1)
    project_path: str
    lockfile_path: str
    lock_before_sha256: str | None = None
    lock_after_sha256: str | None = None
    lock_after_size_bytes: int | None = Field(default=None, ge=1)
    steps: tuple[BootstrapStep, ...]
    preflight_status: BootstrapStatus | None = None
    preflight_report_sha256: str | None = None
    approval_created: bool = False
    report_sha256: str


class CampaignApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    bootstrap_id: str
    profile_name: str
    project_path: str
    lockfile_sha256: str
    preflight_report_sha256: str
    bootstrap_report_sha256: str
    generated_at_utc: str
    campaign_execution_allowed: Literal[True] = True
    approval_sha256: str


def _safe_path(root: Path, relative: str) -> Path:
    repository = root.resolve()
    candidate = (repository / relative).resolve()
    if candidate != repository and repository not in candidate.parents:
        raise RuntimeBootstrapError(f"path escapes repository root: {relative}")
    return candidate


def _text_sha256(value: str) -> str:
    return canonical_sha256({"text": value})


def _status(steps: Sequence[BootstrapStep]) -> BootstrapStatus:
    if any(item.status == "FAIL" for item in steps):
        return "FAIL"
    if any(item.status in {"BLOCKED", "SKIPPED"} for item in steps):
        return "BLOCKED"
    return "PASS"


def _command_step(
    step_id: str,
    command: tuple[str, ...],
    runner: Runner,
    root: Path,
    timeout: int,
    failure_status: Literal["BLOCKED", "FAIL"],
) -> BootstrapStep:
    try:
        result = runner(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return BootstrapStep(
            step_id=step_id,
            status="BLOCKED",
            command=command,
            detail=f"{type(error).__name__}: {error}",
        )
    except Exception as error:
        return BootstrapStep(
            step_id=step_id,
            status="FAIL",
            command=command,
            detail=f"{type(error).__name__}: {error}",
        )
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    return BootstrapStep(
        step_id=step_id,
        status="PASS" if result.returncode == 0 else failure_status,
        command=command,
        returncode=result.returncode,
        stdout_size_bytes=len(stdout.encode()),
        stderr_size_bytes=len(stderr.encode()),
        stdout_sha256=_text_sha256(stdout),
        stderr_sha256=_text_sha256(stderr),
        detail="command completed" if result.returncode == 0 else "command failed",
    )


def _validate_preflight(
    payload: Mapping[str, Any],
    profile_name: str,
    lock_sha256: str,
) -> tuple[BootstrapStatus, str]:
    report_hash = payload.get("report_sha256")
    if not isinstance(report_hash, str):
        raise RuntimeBootstrapError("preflight report_sha256 is missing")
    unsigned = dict(payload)
    unsigned.pop("report_sha256", None)
    if canonical_sha256(unsigned) != report_hash:
        raise RuntimeBootstrapError("preflight report SHA-256 mismatch")
    if payload.get("profile_name") != profile_name:
        raise RuntimeBootstrapError("preflight profile_name mismatch")
    status = payload.get("overall_status")
    if status not in {"PASS", "BLOCKED", "FAIL"}:
        raise RuntimeBootstrapError("preflight overall_status is invalid")
    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise RuntimeBootstrapError("preflight checks must be a list")
    lock_checks = [item for item in checks if item.get("check_id") == "lockfile"]
    if len(lock_checks) != 1:
        raise RuntimeBootstrapError("preflight must contain one lockfile check")
    observed = lock_checks[0].get("observed")
    observed_hash = observed.get("sha256") if isinstance(observed, dict) else None
    if observed_hash != lock_sha256:
        raise RuntimeBootstrapError("preflight lockfile SHA-256 differs from bootstrap")
    return status, report_hash


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def _report(
    profile: RuntimeBootstrapProfile,
    *,
    generated_at: str,
    process_id: int,
    steps: Sequence[BootstrapStep],
    lock_before: str | None,
    lock_after: str | None,
    lock_size: int | None,
    preflight_status: BootstrapStatus | None,
    preflight_hash: str | None,
) -> RuntimeBootstrapReport:
    status = _status(steps)
    payload = {
        "schema_version": 1,
        "bootstrap_id": profile.bootstrap_id,
        "profile_name": profile.profile_name,
        "overall_status": status,
        "generated_at_utc": generated_at,
        "process_id": process_id,
        "project_path": profile.project_path,
        "lockfile_path": profile.lockfile_path,
        "lock_before_sha256": lock_before,
        "lock_after_sha256": lock_after,
        "lock_after_size_bytes": lock_size,
        "steps": [item.model_dump(mode="json") for item in steps],
        "preflight_status": preflight_status,
        "preflight_report_sha256": preflight_hash,
        "approval_created": status == "PASS" and preflight_status == "PASS",
    }
    return RuntimeBootstrapReport(**payload, report_sha256=canonical_sha256(payload))


def _approval(report: RuntimeBootstrapReport) -> CampaignApproval:
    if not report.lock_after_sha256 or not report.preflight_report_sha256:
        raise RuntimeBootstrapError("approval requires lock and preflight hashes")
    payload = {
        "schema_version": 1,
        "bootstrap_id": report.bootstrap_id,
        "profile_name": report.profile_name,
        "project_path": report.project_path,
        "lockfile_sha256": report.lock_after_sha256,
        "preflight_report_sha256": report.preflight_report_sha256,
        "bootstrap_report_sha256": report.report_sha256,
        "generated_at_utc": report.generated_at_utc,
        "campaign_execution_allowed": True,
    }
    return CampaignApproval(**payload, approval_sha256=canonical_sha256(payload))


def run_runtime_bootstrap(
    profile: RuntimeBootstrapProfile,
    repository_root: Path,
    *,
    runner: Runner = subprocess.run,
    uv_locator: Callable[[str], str | None] = shutil.which,
    clock: Clock = lambda: datetime.now(timezone.utc),
    process_id: int | None = None,
) -> tuple[RuntimeBootstrapReport, CampaignApproval | None]:
    root = repository_root.resolve()
    project = _safe_path(root, profile.project_path)
    runtime_profile = _safe_path(root, profile.runtime_profile_path)
    lockfile = _safe_path(root, profile.lockfile_path)
    preflight_output = _safe_path(root, profile.preflight_output_path)
    report_output = _safe_path(root, profile.bootstrap_report_path)
    approval_output = _safe_path(root, profile.approval_path)
    generated_at = clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    pid = process_id or os.getpid()

    for stale in (preflight_output, report_output, approval_output):
        stale.unlink(missing_ok=True)

    steps: list[BootstrapStep] = []
    lock_before = file_sha256(lockfile) if lockfile.is_file() else None
    lock_after: str | None = None
    lock_size: int | None = None
    preflight_status: BootstrapStatus | None = None
    preflight_hash: str | None = None

    project_ok = (project / "pyproject.toml").is_file()
    steps.append(
        BootstrapStep(
            step_id="project_manifest",
            status="PASS" if project_ok else "BLOCKED",
            detail="project manifest exists" if project_ok else "pyproject.toml is missing",
        )
    )
    profile_ok = runtime_profile.is_file()
    steps.append(
        BootstrapStep(
            step_id="runtime_profile",
            status="PASS" if profile_ok else "BLOCKED",
            detail="runtime profile exists" if profile_ok else "runtime profile is missing",
        )
    )
    uv_path = uv_locator(profile.uv_executable)
    steps.append(
        BootstrapStep(
            step_id="uv_executable",
            status="PASS" if uv_path else "BLOCKED",
            command=(uv_path or profile.uv_executable,),
            detail="uv resolved" if uv_path else "uv executable is unavailable",
        )
    )

    if _status(steps) == "PASS":
        lock_command = (
            uv_path,
            "lock",
            "--project",
            str(project),
            "--python",
            profile.python_version,
        )
        steps.append(
            _command_step(
                "uv_lock",
                lock_command,
                runner,
                root,
                profile.timeout_seconds,
                "BLOCKED",
            )
        )

    if _status(steps) == "PASS":
        lock_ok = lockfile.is_file() and lockfile.stat().st_size > 0
        if lock_ok:
            lock_after = file_sha256(lockfile)
            lock_size = lockfile.stat().st_size
        steps.append(
            BootstrapStep(
                step_id="lockfile_after_lock",
                status="PASS" if lock_ok else "FAIL",
                detail="uv.lock hashed" if lock_ok else "non-empty uv.lock was not created",
            )
        )

    if _status(steps) == "PASS":
        sync_command = (
            uv_path,
            "sync",
            "--project",
            str(project),
            "--frozen",
            "--python",
            profile.python_version,
        )
        steps.append(
            _command_step(
                "uv_sync_frozen",
                sync_command,
                runner,
                root,
                profile.timeout_seconds,
                "BLOCKED",
            )
        )

    if _status(steps) == "PASS":
        preflight_command = (
            uv_path,
            "run",
            "--project",
            str(project),
            "--frozen",
            "python",
            str(root / "scripts/run_darts_runtime_preflight.py"),
            "--profile",
            str(runtime_profile),
            "--repository-root",
            str(root),
            "--output",
            str(preflight_output),
        )
        step = _command_step(
            "runtime_preflight",
            preflight_command,
            runner,
            root,
            profile.timeout_seconds,
            "FAIL",
        )
        if not preflight_output.is_file():
            step = step.model_copy(
                update={"status": "FAIL", "detail": "preflight JSON was not created"}
            )
        else:
            try:
                payload = json.loads(preflight_output.read_text(encoding="utf-8"))
                preflight_status, preflight_hash = _validate_preflight(
                    payload,
                    profile.profile_name,
                    lock_after or "",
                )
                expected_code = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[preflight_status]
                if step.returncode != expected_code:
                    raise RuntimeBootstrapError("preflight exit code and JSON status disagree")
            except Exception as error:
                step = step.model_copy(
                    update={"status": "FAIL", "detail": f"invalid preflight report: {error}"}
                )
            else:
                step = step.model_copy(
                    update={"status": preflight_status, "detail": f"preflight {preflight_status}"}
                )
        steps.append(step)

    report = _report(
        profile,
        generated_at=generated_at,
        process_id=pid,
        steps=steps,
        lock_before=lock_before,
        lock_after=lock_after,
        lock_size=lock_size,
        preflight_status=preflight_status,
        preflight_hash=preflight_hash,
    )
    _write_json(report_output, report.model_dump(mode="json"))
    token: CampaignApproval | None = None
    if report.approval_created:
        token = _approval(report)
        _write_json(approval_output, token.model_dump(mode="json"))
    else:
        approval_output.unlink(missing_ok=True)
    return report, token


def load_bootstrap_profile(path: Path) -> RuntimeBootstrapProfile:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RuntimeBootstrapProfile.model_validate(raw)
