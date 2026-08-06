from __future__ import annotations

import hashlib
import json
import os
import shlex
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.timesfm25_campaign.certification_bundle import (
    atomic_write_text,
    sha256_file,
    validate_run_id,
    verify_sha256_manifest,
)

_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_TERMINAL_RUNTIME_STATUSES = {
    "VERIFIED_CPU",
    "VERIFIED_GPU",
    "PARTIALLY_VERIFIED_GPU",
    "FAILED",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def default_run_id(now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    value = f"timesfm25-native-{moment.strftime('%Y%m%dT%H%M%SZ')}"
    return validate_run_id(value)


def tmux_session_name(run_id: str) -> str:
    validated = validate_run_id(run_id)
    safe = validated.replace(".", "-").replace("_", "-")
    value = f"tfm25-{safe}"
    if len(value) <= 120:
        return value
    suffix = hashlib.sha256(validated.encode("utf-8")).hexdigest()[:12]
    return f"{value[:107]}-{suffix}"


def create_request_payload(
    template_path: Path,
    *,
    run_id: str,
    snapshot_path: Path,
) -> dict[str, Any]:
    validate_run_id(run_id)
    snapshot = snapshot_path.expanduser()
    if not snapshot.is_absolute():
        raise ValueError("snapshot_path must be absolute")
    snapshot = snapshot.resolve(strict=False)
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("request template must contain a JSON object")
    if payload.get("schema_version") != 2:
        raise ValueError("request template must use schema_version=2")
    if payload.get("local_files_only") is not True:
        raise ValueError("request template must keep local_files_only=true")
    if payload.get("backend") not in {"pytorch_native", "pytorch_source"}:
        raise ValueError("target-host operator supports only native PyTorch backends")
    payload["run_id"] = run_id
    payload["snapshot_path"] = str(snapshot)
    payload["device"] = "cuda"
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)


def build_runner_script(
    *,
    project_root: Path,
    request_path: Path,
    environment: Path,
    output_root: Path,
    control_dir: Path,
    timeout: int,
    preflight_timeout: int,
) -> str:
    if timeout < 1 or preflight_timeout < 1:
        raise ValueError("timeouts must be >= 1")
    values = {
        "ROOT": project_root.resolve(),
        "REQUEST": request_path.resolve(),
        "ENVIRONMENT": environment.resolve(),
        "OUTPUT_ROOT": output_root.resolve(),
        "CONTROL_DIR": control_dir.resolve(),
    }
    assignments = "\n".join(
        f"{name}={shlex.quote(str(value))}" for name, value in values.items()
    )
    return f"""#!/usr/bin/env bash
set -Eeuo pipefail

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export UV_OFFLINE=1
export PIP_NO_INDEX=1

{assignments}
CONSOLE_LOG="$CONTROL_DIR/runtime.console.log"
EXIT_FILE="$CONTROL_DIR/operator_exit_code.txt"
FINISHED_FILE="$CONTROL_DIR/operator_finished_at.txt"

mkdir -p "$CONTROL_DIR"
cd "$ROOT"
set +e
uv run --project "$ROOT" python "$ROOT/scripts/run_timesfm25_runtime_certification.py" \\
  --request "$REQUEST" \\
  --environment "$ENVIRONMENT" \\
  --output-root "$OUTPUT_ROOT" \\
  --preflight-timeout {preflight_timeout} \\
  --timeout {timeout} \\
  > >(tee "$CONSOLE_LOG") 2>&1
rc=$?
set -e
printf '%s\n' "$rc" > "$EXIT_FILE"
date -u +%Y-%m-%dT%H:%M:%SZ > "$FINISHED_FILE"
exit "$rc"
"""


def write_runner_script(path: Path, content: str) -> None:
    atomic_write_text(path, content)
    path.chmod(0o700)


def tmux_launch_command(session_name: str, runner_path: Path) -> list[str]:
    if not session_name or len(session_name) > 120:
        raise ValueError("invalid tmux session name")
    return ["tmux", "new-session", "-d", "-s", session_name, "bash", str(runner_path)]


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def inspect_runtime_bundle(run_dir: Path, *, tmux_alive: bool) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    status_path = run_dir / "status.txt"
    certification = _read_json_object(run_dir / "runtime_certification.json")
    manifest_path = run_dir / "SHA256SUMS"
    manifest_ok: bool | None = None
    failures: tuple[str, ...] = ()
    if manifest_path.is_file():
        manifest_ok, failures = verify_sha256_manifest(run_dir)

    runtime_status = None
    if status_path.is_file():
        runtime_status = status_path.read_text(encoding="utf-8").strip()
    if runtime_status in _TERMINAL_RUNTIME_STATUSES:
        if manifest_ok is not True:
            operator_status = "CORRUPT"
        elif runtime_status in {"VERIFIED_CPU", "VERIFIED_GPU"}:
            operator_status = "COMPLETED"
        elif runtime_status == "PARTIALLY_VERIFIED_GPU":
            operator_status = "PARTIAL"
        else:
            operator_status = "FAILED"
    elif tmux_alive:
        operator_status = "RUNNING"
    elif run_dir.exists():
        operator_status = "INCOMPLETE"
    else:
        operator_status = "NOT_STARTED"

    return {
        "schema_version": 1,
        "captured_at": utc_now(),
        "run_dir": str(run_dir),
        "operator_status": operator_status,
        "runtime_status": runtime_status,
        "tmux_alive": tmux_alive,
        "manifest_present": manifest_path.is_file(),
        "manifest_ok": manifest_ok,
        "manifest_failures": list(failures),
        "certification": certification,
    }


def create_deterministic_zip(
    run_dir: Path,
    archive_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    archive_path = archive_path.resolve()
    if archive_path.is_relative_to(run_dir):
        raise ValueError("archive must be outside the sealed runtime bundle")
    if archive_path.exists() and not force:
        raise FileExistsError(f"archive already exists: {archive_path}")
    manifest_ok, failures = verify_sha256_manifest(run_dir)
    if not manifest_ok:
        raise ValueError(f"runtime bundle is not sealed or valid: {failures}")

    files = sorted(path for path in run_dir.rglob("*") if path.is_file())
    for path in files:
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed in archive: {path}")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_name(f".{archive_path.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for path in files:
                relative = path.relative_to(run_dir).as_posix()
                info = zipfile.ZipInfo(
                    filename=f"{run_dir.name}/{relative}",
                    date_time=_FIXED_ZIP_TIMESTAMP,
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (0o100644 & 0xFFFF) << 16
                archive.writestr(info, path.read_bytes())
        os.replace(temporary, archive_path)
    finally:
        temporary.unlink(missing_ok=True)

    digest = sha256_file(archive_path)
    sidecar = archive_path.with_suffix(archive_path.suffix + ".sha256")
    atomic_write_text(sidecar, f"{digest}  {archive_path.name}\n")
    return {
        "archive_path": str(archive_path),
        "sha256_path": str(sidecar),
        "sha256": digest,
        "file_count": len(files),
    }
