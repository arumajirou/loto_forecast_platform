from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import traceback
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .runtime_lane_artifacts import (
    atomic_write,
    sha256_bytes,
    sha256_file,
    utc_now,
    verify_portable_sha256sums,
    write_json,
)
from .runtime_lane_execution import execute_runtime_lane
from .runtime_lane_wheel_policy import prepare_offline_bundle, verify_offline_bundle


@dataclass(frozen=True)
class TargetHostResult:
    controller_dir: Path
    archive_path: Path
    archive_sha256_path: Path
    status: str


def _capture(command: list[str], *, cwd: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def collect_target_host_preflight(
    repo_root: Path,
    *,
    uv_executable: str = "uv",
) -> dict[str, Any]:
    dns: dict[str, dict[str, Any]] = {}
    for host in ("pypi.org", "files.pythonhosted.org"):
        try:
            addresses = sorted(
                {
                    item[4][0]
                    for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                }
            )
            dns[host] = {"status": "PASS", "addresses": addresses}
        except OSError as exc:
            dns[host] = {
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    git_head = _capture(["git", "rev-parse", "HEAD"], cwd=repo_root)
    git_branch = _capture(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
    )
    git_status = _capture(["git", "status", "--short"], cwd=repo_root)
    uv_version = _capture([uv_executable, "--version"], cwd=repo_root)
    python_ok = sys.version_info[:2] == (3, 13)
    return {
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "repo_root": str(repo_root.resolve()),
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "is_python_3_13": python_ok,
        },
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "uv": uv_version,
        "git_head": git_head,
        "git_branch": git_branch,
        "git_status": git_status,
        "dns": dns,
        "working_tree_clean": not bool(git_status.get("stdout")),
        "status": (
            "PASS"
            if python_ok
            and uv_version.get("returncode") == 0
            and git_head.get("returncode") == 0
            else "FAILED"
        ),
    }


def _write_target_host_sums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path == root / "SHA256SUMS":
            continue
        relative = path.relative_to(root).as_posix()
        rows.append(f"{sha256_file(path)}  {relative}")
    atomic_write(
        root / "SHA256SUMS",
        ("\n".join(rows) + "\n").encode("utf-8"),
    )


def _safe_member_name(name: str) -> bool:
    posix = PurePosixPath(name)
    return bool(posix.parts) and not posix.is_absolute() and ".." not in posix.parts


def create_deterministic_zip(source_dir: Path) -> Path:
    archive = source_dir.with_suffix(".zip")
    temporary = archive.with_name(f".{archive.name}.{os.getpid()}.tmp")
    prefix = source_dir.name
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as bundle:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(f"{prefix}/{relative}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    temporary.replace(archive)
    sidecar = archive.with_suffix(".zip.sha256")
    atomic_write(
        sidecar,
        f"{sha256_file(archive)}  {archive.name}\n".encode("utf-8"),
    )
    return archive


def verify_target_host_package(archive: Path) -> dict[str, Any]:
    failures: list[str] = []
    sidecar = archive.with_suffix(".zip.sha256")
    if not archive.is_file() or archive.is_symlink():
        return {"status": "FAILED", "failures": ["archive is missing or symlinked"]}
    if not sidecar.is_file() or sidecar.is_symlink():
        return {"status": "FAILED", "failures": ["archive SHA-256 sidecar is missing"]}
    try:
        digest, filename = sidecar.read_text(encoding="utf-8").strip().split("  ", 1)
    except ValueError:
        failures.append("archive SHA-256 sidecar is malformed")
    else:
        if filename != archive.name:
            failures.append("archive SHA-256 sidecar filename mismatch")
        if digest != sha256_file(archive):
            failures.append("archive SHA-256 mismatch")
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)):
                failures.append("archive contains duplicate members")
            if not names or any(not _safe_member_name(name) for name in names):
                failures.append("archive contains unsafe members")
            prefixes = {PurePosixPath(name).parts[0] for name in names if name}
            if len(prefixes) != 1:
                failures.append("archive must contain one run prefix")
            if prefixes:
                prefix = next(iter(prefixes))
                checksum_name = f"{prefix}/SHA256SUMS"
                if checksum_name not in names:
                    failures.append("archive does not contain root SHA256SUMS")
                else:
                    checksum_rows = bundle.read(checksum_name).decode("utf-8").splitlines()
                    expected = {checksum_name}
                    for line_number, raw in enumerate(checksum_rows, 1):
                        if not raw.strip():
                            continue
                        try:
                            item_digest, relative = raw.split("  ", 1)
                        except ValueError:
                            failures.append(
                                f"SHA256SUMS line {line_number} is malformed"
                            )
                            continue
                        if not _safe_member_name(relative):
                            failures.append(
                                f"SHA256SUMS line {line_number} has unsafe path"
                            )
                            continue
                        member = f"{prefix}/{relative}"
                        expected.add(member)
                        if member not in names:
                            failures.append(f"archive member missing: {relative}")
                            continue
                        if sha256_bytes(bundle.read(member)) != item_digest:
                            failures.append(f"archive member digest mismatch: {relative}")
                    extras = set(names).difference(expected)
                    if extras:
                        failures.append(
                            f"archive contains unchecksummed members: {sorted(extras)}"
                        )
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        failures.append(f"archive verification error: {type(exc).__name__}: {exc}")
    return {
        "status": "PASS" if not failures else "FAILED",
        "failures": failures,
        "archive": str(archive),
        "archive_sha256": sha256_file(archive),
    }


def run_target_host_certification(
    repo_root: Path,
    output_root: Path,
    *,
    run_id: str | None = None,
    wheelhouse: Path | None = None,
    prepare_offline: bool = False,
    offline: bool = False,
    uv_executable: str = "uv",
    horizon: int = 1,
    seed: int = 1,
    preflight_fn: Callable[..., dict[str, Any]] = collect_target_host_preflight,
    prepare_fn: Callable[..., Path] = prepare_offline_bundle,
    execute_fn: Callable[..., Path] = execute_runtime_lane,
) -> TargetHostResult:
    if offline and wheelhouse is None:
        raise ValueError("offline target-host execution requires --wheelhouse")
    if prepare_offline and wheelhouse is None:
        raise ValueError("--prepare-offline requires --wheelhouse")
    run_id = run_id or datetime.now(timezone.utc).strftime(
        "statsforecast-target-%Y%m%d-%H%M%S"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    controller_dir = output_root / run_id
    controller_dir.mkdir(parents=False, exist_ok=False)
    preflight = preflight_fn(repo_root, uv_executable=uv_executable)
    write_json(controller_dir / "TARGET_HOST_PREFLIGHT.json", preflight)
    status = "FAILED"
    runtime_dir: Path | None = None
    wheelhouse_report: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    try:
        if prepare_offline:
            prepare_fn(
                repo_root,
                wheelhouse,
                uv_executable=uv_executable,
            )
        if wheelhouse is not None:
            wheelhouse_report = verify_offline_bundle(wheelhouse)
            if offline and wheelhouse_report["status"] != "PASS":
                raise RuntimeError(
                    f"offline wheelhouse verification failed: "
                    f"{wheelhouse_report['failures']}"
                )
        runtime_dir = execute_fn(
            repo_root,
            controller_dir / "runtime-runs",
            run_id="runtime",
            wheelhouse=wheelhouse,
            offline=offline,
            uv_executable=uv_executable,
            horizon=horizon,
            seed=seed,
        )
        runtime_report_path = runtime_dir / "RUNTIME_LANE_REPORT.json"
        runtime_report = json.loads(runtime_report_path.read_text(encoding="utf-8"))
        status = "PASS" if runtime_report.get("status") == "PASS" else "FAILED"
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "started_at_utc": preflight.get("captured_at_utc"),
        "finished_at_utc": utc_now(),
        "repo_root": str(repo_root.resolve()),
        "runtime_dir": str(runtime_dir) if runtime_dir is not None else None,
        "wheelhouse": str(wheelhouse.resolve()) if wheelhouse is not None else None,
        "wheelhouse_verification": wheelhouse_report,
        "offline": offline,
        "prepare_offline": prepare_offline,
        "horizon": horizon,
        "seed": seed,
        "preflight_status": preflight.get("status"),
        "holdout_opened": False,
        "prospective_actual_known": False,
        "error": error,
    }
    write_json(controller_dir / "TARGET_HOST_REPORT.json", report)
    files = []
    for path in sorted(controller_dir.rglob("*")):
        if path.is_file() and path.name not in {
            "TARGET_HOST_ARTIFACT_MANIFEST.json",
            "SHA256SUMS",
        }:
            files.append(
                {
                    "path": path.relative_to(controller_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    write_json(
        controller_dir / "TARGET_HOST_ARTIFACT_MANIFEST.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": status,
            "created_at_utc": utc_now(),
            "artifact_count": len(files),
            "artifacts": files,
        },
    )
    _write_target_host_sums(controller_dir)
    checksum_report = verify_portable_sha256sums(controller_dir)
    if checksum_report["status"] != "PASS":
        raise RuntimeError(
            f"target-host evidence checksum verification failed: "
            f"{checksum_report['failures']}"
        )
    archive = create_deterministic_zip(controller_dir)
    package_report = verify_target_host_package(archive)
    if package_report["status"] != "PASS":
        raise RuntimeError(
            f"target-host package verification failed: {package_report['failures']}"
        )
    return TargetHostResult(
        controller_dir=controller_dir,
        archive_path=archive,
        archive_sha256_path=archive.with_suffix(".zip.sha256"),
        status=status,
    )


__all__ = [
    "TargetHostResult",
    "collect_target_host_preflight",
    "create_deterministic_zip",
    "run_target_host_certification",
    "verify_target_host_package",
]
