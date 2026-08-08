"""Verification reports, environment evidence, manifests, and SHA-256 files."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db_runtime_verification_checks import evaluate_database_runtime_run, sha256_file
from .db_runtime_verification_models import (
    ArtifactManifest,
    DatabaseRuntimeVerificationReport,
)

_OUTPUTS = {
    "VERIFICATION_REPORT.json",
    "VERIFICATION_SUMMARY.txt",
    "RUNTIME_VERIFICATION_ENVIRONMENT.json",
    "ARTIFACT_MANIFEST.json",
    "SHA256SUMS",
}


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    _atomic_write(path, data)


def collect_verification_environment(run_directory: str | Path) -> dict[str, Any]:
    """Collect verifier-host context without relabeling it as execution proof."""

    run_dir = Path(run_directory).resolve()
    packages: dict[str, str | None] = {}
    for name in ("neuralforecast", "torch", "ray", "optuna", "numpy", "pandas", "pydantic"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None

    def command(*args: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                args,
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
        return {
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }

    return {
        "schema_version": "1.0.0",
        "created_at": datetime.now(UTC).isoformat(),
        "purpose": "verification-host context; not model runtime certification",
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "git_head": command("git", "rev-parse", "HEAD"),
        "git_status": command("git", "status", "--short"),
        "uv_version": command("uv", "--version"),
        "nvidia_smi": command(
            "nvidia-smi",
            "--query-gpu=index,name,uuid,driver_version,memory.total,memory.used",
            "--format=csv,noheader,nounits",
        ),
    }


def _critical_paths(run_dir: Path, report: DatabaseRuntimeVerificationReport) -> list[Path]:
    paths = [
        run_dir / "campaign_plan.json",
        run_dir / "campaign_report.json",
        run_dir / "input_panel.csv",
    ]
    for model in report.model_results:
        paths.extend(run_dir / relative for relative in model.critical_artifacts)
    unique = {path.resolve(): path for path in paths if path.is_file()}
    return sorted(unique.values(), key=lambda path: path.relative_to(run_dir).as_posix())


def _write_summary(path: Path, report: DatabaseRuntimeVerificationReport) -> None:
    lines = [
        f"STATUS={report.status}",
        f"RUN_DIRECTORY={report.run_directory}",
        f"REQUIRE_GPU={str(report.require_gpu).lower()}",
        f"EXPECTED_MODEL_COUNT={report.expected_model_count}",
        f"OBSERVED_MODEL_COUNT={report.observed_model_count}",
        f"CAMPAIGN_STATUS={report.campaign_status}",
        f"CERTIFICATION_STATUS={report.certification_status}",
        f"SEARCH_SPACE_ARTIFACT_STATUS={report.search_space_artifact_status}",
        f"FAILURE_COUNT={len(report.failures)}",
    ]
    for failure in report.failures:
        lines.append(f"FAILURE={failure}")
    for model in report.model_results:
        lines.append(f"MODEL={model.model_id}:{model.status}")
        for failure in model.failures:
            lines.append(f"MODEL_FAILURE={model.model_id}:{failure}")
    _atomic_write(path, ("\n".join(lines) + "\n").encode("utf-8"))


def _write_sha256s(run_dir: Path, paths: Sequence[Path]) -> None:
    records = [
        f"{sha256_file(path)}  {path.relative_to(run_dir).as_posix()}"
        for path in sorted(paths, key=lambda item: item.relative_to(run_dir).as_posix())
    ]
    _atomic_write(run_dir / "SHA256SUMS", ("\n".join(records) + "\n").encode("utf-8"))


def verify_sha256s(run_directory: str | Path) -> list[str]:
    run_dir = Path(run_directory).resolve()
    checksum_path = run_dir / "SHA256SUMS"
    if not checksum_path.is_file():
        return ["SHA256SUMS is missing"]
    failures: list[str] = []
    for line_number, line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            failures.append(f"invalid SHA256SUMS line {line_number}")
            continue
        expected, relative = fields
        relative_path = Path(relative.strip())
        if relative_path.is_absolute():
            failures.append(f"unsafe checksum target: {relative}")
            continue
        path = (run_dir / relative_path).resolve()
        try:
            path.relative_to(run_dir)
        except ValueError:
            failures.append(f"unsafe checksum target: {relative}")
            continue
        if not path.is_file():
            failures.append(f"missing checksum target: {relative}")
        elif sha256_file(path) != expected:
            failures.append(f"checksum mismatch: {relative}")
    return failures


def write_database_runtime_verification(
    run_directory: str | Path,
    *,
    expected_model_count: int | None = None,
    require_gpu: bool | None = None,
) -> DatabaseRuntimeVerificationReport:
    """Evaluate a run and write report, environment, manifest, summary, and hashes."""

    run_dir = Path(run_directory).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in _OUTPUTS:
        path = run_dir / name
        if path.is_file():
            path.unlink()
    report = evaluate_database_runtime_run(
        run_dir,
        expected_model_count=expected_model_count,
        require_gpu=require_gpu,
    )
    report_path = run_dir / "VERIFICATION_REPORT.json"
    _write_json(report_path, report.model_dump(mode="json"))
    environment_path = run_dir / "RUNTIME_VERIFICATION_ENVIRONMENT.json"
    _write_json(environment_path, collect_verification_environment(run_dir))
    summary_path = run_dir / "VERIFICATION_SUMMARY.txt"
    _write_summary(summary_path, report)

    critical = _critical_paths(run_dir, report)
    critical.extend([report_path, environment_path, summary_path])
    manifest = ArtifactManifest(
        created_at=datetime.now(UTC).isoformat(),
        run_directory=str(run_dir),
        verification_status=report.status,
        files=tuple(
            {
                "path": path.relative_to(run_dir).as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(critical, key=lambda item: item.relative_to(run_dir).as_posix())
        ),
    )
    manifest_path = run_dir / "ARTIFACT_MANIFEST.json"
    _write_json(manifest_path, manifest.model_dump(mode="json"))
    _write_sha256s(run_dir, [*critical, manifest_path])
    checksum_failures = verify_sha256s(run_dir)
    if checksum_failures:
        raise RuntimeError(f"verification SHA256 failure: {checksum_failures}")
    return report
