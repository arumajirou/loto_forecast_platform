from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

_RETRYABLE = {
    "CONFIGURATION",
    "DEPENDENCY_OR_NETWORK",
    "MODEL_RUNTIME",
    "EVIDENCE_INTEGRITY",
    "ADMISSION_REJECTED",
    "TARGET_HOST_RUNTIME",
}
_MANUAL = {"GIT_PREFLIGHT", "UNKNOWN"}


@dataclass(frozen=True)
class RemediationExecutionResult:
    run_id: str
    output_dir: Path
    report_path: Path
    plan_path: Path
    archive_path: Path
    archive_sha256_path: Path
    status: str
    decision: str
    formal_pass: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _write_json(path: Path, payload: Any) -> None:
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    _atomic_write(path, content)


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe checksum path: {value}")
    return Path(*pure.parts)


def verify_triage_evidence(triage_dir: Path) -> dict[str, Any]:
    if not triage_dir.is_dir() or triage_dir.is_symlink():
        raise ValueError(f"invalid triage directory: {triage_dir}")
    sums_path = triage_dir / "SHA256SUMS"
    if not sums_path.is_file() or sums_path.is_symlink():
        raise ValueError("missing safe triage SHA256SUMS")
    expected: dict[Path, str] = {}
    failures: list[str] = []
    for raw_line in sums_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        digest, separator, relative_text = raw_line.partition("  ")
        if not separator or len(digest) != 64:
            failures.append(f"invalid checksum row: {raw_line}")
            continue
        try:
            relative = _safe_relative(relative_text)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        if relative in expected:
            failures.append(f"duplicate checksum entry: {relative.as_posix()}")
            continue
        expected[relative] = digest.lower()
    actual = {
        path.relative_to(triage_dir)
        for path in triage_dir.rglob("*")
        if path.is_file() and path != sums_path
    }
    missing_entries = sorted(actual.difference(expected))
    extra_entries = sorted(set(expected).difference(actual))
    failures.extend(f"unchecksummed file: {path.as_posix()}" for path in missing_entries)
    failures.extend(f"missing file: {path.as_posix()}" for path in extra_entries)
    for relative, digest in expected.items():
        path = triage_dir / relative
        if not path.is_file() or path.is_symlink():
            failures.append(f"invalid evidence file: {relative.as_posix()}")
        elif _sha256_file(path) != digest:
            failures.append(f"digest mismatch: {relative.as_posix()}")
    return {
        "status": "PASS" if not failures else "FAILED",
        "failures": failures,
        "verified_files": len(expected) - len(extra_entries),
    }


def _valid_commit(value: str) -> bool:
    normalized = value.lower()
    return len(normalized) == 40 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _git_context(repo_root: Path) -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "head": head.stdout.strip().lower() if head.returncode == 0 else None,
        "head_returncode": head.returncode,
        "working_tree_clean": status.returncode == 0 and not status.stdout.strip(),
        "status_returncode": status.returncode,
        "status_porcelain": status.stdout.splitlines(),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# StatsForecast Remediation Execution",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{report['decision']}`",
        f"- Formal pass: `{str(report['formal_pass']).lower()}`",
        f"- Source classification: `{report['source_classification']}`",
        f"- Attempts: `{len(report['attempts'])}`",
        "",
        "## Attempts",
        "",
    ]
    if report["attempts"]:
        for attempt in report["attempts"]:
            lines.append(
                f"- Attempt {attempt['attempt']}: decision={attempt['decision']}, "
                f"formal_pass={str(attempt['formal_pass']).lower()}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Failures", ""])
    failures = report.get("failures") or []
    lines.extend(f"- {failure}" for failure in failures)
    if not failures:
        lines.append("- None")
    lines.extend(
        [
            "",
            "This executor never runs command strings from the triage plan and never mutates Git.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_sums(root: Path) -> Path:
    checksum_path = root / "SHA256SUMS"
    rows: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and path != checksum_path:
            rows.append(f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}")
    _atomic_write(checksum_path, ("\n".join(rows) + "\n").encode("utf-8"))
    return checksum_path


def _write_deterministic_zip(source: Path, archive: Path) -> tuple[Path, Path]:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = Path(source.name) / path.relative_to(source)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    _atomic_write(sidecar, f"{_sha256_file(archive)}  {archive.name}\n".encode("utf-8"))
    return archive, sidecar


def _resolve_source_dir(
    triage_dir: Path,
    classification: dict[str, Any],
    source_end_to_end_dir: Path | None,
) -> Path:
    if source_end_to_end_dir is not None:
        candidate = source_end_to_end_dir
    else:
        candidate = Path(str(classification.get("source_end_to_end_dir") or ""))
    if not candidate.is_dir() or candidate.is_symlink():
        raise ValueError("source end-to-end directory is missing or unsafe")
    report_path = candidate / "END_TO_END_REPORT.json"
    if not report_path.is_file() or report_path.is_symlink():
        raise ValueError("source END_TO_END_REPORT.json is missing or unsafe")
    expected_digest = classification.get("source_report_sha256")
    if expected_digest and _sha256_file(report_path) != expected_digest:
        raise ValueError("source END_TO_END_REPORT.json digest mismatch")
    return candidate


def execute_bounded_remediation(
    repo_root: Path,
    triage_dir: Path,
    output_root: Path,
    *,
    source_end_to_end_dir: Path | None = None,
    wheelhouse: Path | None = None,
    run_id: str | None = None,
    prepare_offline: bool = False,
    offline: bool = False,
    expected_commit: str,
    expected_seed: int = 1,
    horizon: int = 1,
    max_attempts: int = 1,
    uv_executable: str = "uv",
    end_to_end_runner: Callable[..., Any] | None = None,
    git_context_fn: Callable[[Path], dict[str, Any]] = _git_context,
) -> RemediationExecutionResult:
    if prepare_offline and offline:
        raise ValueError("--prepare-offline and --offline are mutually exclusive")
    if (prepare_offline or offline) and wheelhouse is None:
        raise ValueError("wheelhouse is required for selected execution mode")
    if not _valid_commit(expected_commit):
        raise ValueError("expected_commit must be a full 40-character SHA")
    if expected_seed < 0 or horizon < 1:
        raise ValueError("seed and horizon must be valid fixed values")
    if not 1 <= max_attempts <= 3:
        raise ValueError("max_attempts must be between 1 and 3")

    verification = verify_triage_evidence(triage_dir)
    if verification["status"] != "PASS":
        raise ValueError(f"triage evidence verification failed: {verification['failures']}")
    classification = _load_object(triage_dir / "FAILURE_CLASSIFICATION.json")
    remediation = _load_object(triage_dir / "REMEDIATION_PLAN.json")
    source_dir = _resolve_source_dir(triage_dir, classification, source_end_to_end_dir)
    source_classification = str(classification.get("primary_classification"))

    run_id = run_id or datetime.now(timezone.utc).strftime(
        "statsforecast-remediation-%Y%m%d-%H%M%S"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    output_dir = output_root / run_id
    output_dir.mkdir(parents=False, exist_ok=False)
    plan_path = output_dir / "REMEDIATION_EXECUTION_PLAN.json"
    report_path = output_dir / "REMEDIATION_EXECUTION_REPORT.json"

    policy = {
        "schema_version": 1,
        "run_id": run_id,
        "source_triage_dir": str(triage_dir.resolve()),
        "source_end_to_end_dir": str(source_dir.resolve()),
        "source_classification": source_classification,
        "triage_evidence_verification": verification,
        "remediation_plan_sha256": _sha256_file(triage_dir / "REMEDIATION_PLAN.json"),
        "commands_from_triage_executed": False,
        "git_mutation_allowed": False,
        "parameter_mutation_allowed": False,
        "expected_commit": expected_commit.lower(),
        "expected_seed": expected_seed,
        "horizon": horizon,
        "max_attempts": max_attempts,
        "prepare_offline": prepare_offline,
        "offline": offline,
        "wheelhouse": str(wheelhouse.resolve()) if wheelhouse else None,
        "created_at_utc": _utc_now(),
    }
    _write_json(plan_path, policy)

    attempts: list[dict[str, Any]] = []
    failures: list[str] = []
    formal_pass = False
    decision = "MERGE_BLOCKED"
    status = "MANUAL_ACTION_REQUIRED"

    if source_classification == "NO_FAILURE":
        status = "NOT_REQUIRED"
        decision = "RUNTIME_CERTIFIED"
        formal_pass = True
    elif source_classification in _MANUAL:
        failures.append(f"automatic remediation is prohibited for {source_classification}")
    elif source_classification not in _RETRYABLE:
        failures.append(f"unsupported remediation classification: {source_classification}")
    else:
        git_context = git_context_fn(repo_root)
        actual_commit = git_context.get("head")
        if actual_commit != expected_commit.lower():
            failures.append(
                f"Git HEAD mismatch: expected {expected_commit.lower()}, got {actual_commit}"
            )
        if not git_context.get("working_tree_clean"):
            failures.append("working tree is not clean")
        if not failures:
            if end_to_end_runner is None:
                from .runtime_lane_end_to_end import run_end_to_end_certification

                end_to_end_runner = run_end_to_end_certification
            status = "REMEDIATION_EXHAUSTED"
            for attempt_number in range(1, max_attempts + 1):
                attempt_id = f"attempt-{attempt_number:02d}"
                try:
                    result = end_to_end_runner(
                        repo_root,
                        output_dir / "attempts",
                        wheelhouse=wheelhouse,
                        run_id=attempt_id,
                        prepare_offline=prepare_offline,
                        offline=offline,
                        expected_commit=expected_commit.lower(),
                        expected_seed=expected_seed,
                        horizon=horizon,
                        uv_executable=uv_executable,
                    )
                    attempt = {
                        "attempt": attempt_number,
                        "run_id": result.run_id,
                        "output_dir": str(result.output_dir),
                        "report_path": str(result.report_path),
                        "decision": result.decision,
                        "formal_pass": bool(result.formal_pass),
                        "exception": None,
                    }
                except Exception as exc:  # evidence retention boundary
                    attempt = {
                        "attempt": attempt_number,
                        "run_id": attempt_id,
                        "output_dir": None,
                        "report_path": None,
                        "decision": "MERGE_BLOCKED",
                        "formal_pass": False,
                        "exception": {"type": type(exc).__name__, "message": str(exc)},
                    }
                attempts.append(attempt)
                if attempt["formal_pass"]:
                    formal_pass = True
                    decision = "RUNTIME_CERTIFIED"
                    status = "RUNTIME_CERTIFIED"
                    break
            if not formal_pass:
                failures.append(f"bounded remediation exhausted after {len(attempts)} attempt(s)")

    report = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "decision": decision,
        "formal_pass": formal_pass,
        "source_classification": source_classification,
        "source_classification_sha256": _sha256_file(triage_dir / "FAILURE_CLASSIFICATION.json"),
        "attempts": attempts,
        "failures": failures,
        "commands_from_triage_executed": False,
        "git_mutated": False,
        "parameters_mutated": False,
        "finished_at_utc": _utc_now(),
    }
    _write_json(report_path, report)
    _atomic_write(
        output_dir / "REMEDIATION_EXECUTION_REPORT.md",
        _render_markdown(report).encode("utf-8"),
    )
    _write_sums(output_dir)
    archive_path = output_root / f"{run_id}.zip"
    archive_path, sidecar = _write_deterministic_zip(output_dir, archive_path)
    return RemediationExecutionResult(
        run_id=run_id,
        output_dir=output_dir,
        report_path=report_path,
        plan_path=plan_path,
        archive_path=archive_path,
        archive_sha256_path=sidecar,
        status=status,
        decision=decision,
        formal_pass=formal_pass,
    )


__all__ = [
    "RemediationExecutionResult",
    "execute_bounded_remediation",
    "verify_triage_evidence",
]
