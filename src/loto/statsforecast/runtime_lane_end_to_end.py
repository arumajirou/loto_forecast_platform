from __future__ import annotations

import hashlib
import json
import os
import subprocess
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class EndToEndResult:
    run_id: str
    output_dir: Path
    report_path: Path
    admission_dir: Path | None
    archive_path: Path | None
    expected_commit: str | None
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
    content = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    _atomic_write(path, content)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_sums(root: Path) -> Path:
    rows: list[str] = []
    checksum_path = root / "SHA256SUMS"
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and path != checksum_path:
            relative = path.relative_to(root).as_posix()
            rows.append(f"{_sha256_file(path)}  {relative}")
    _atomic_write(checksum_path, ("\n".join(rows) + "\n").encode("utf-8"))
    return checksum_path


def _valid_commit(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def resolve_git_context(repo_root: Path) -> dict[str, Any]:
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
    resolved = head.stdout.strip().lower()
    return {
        "head": resolved if head.returncode == 0 and _valid_commit(resolved) else None,
        "head_returncode": head.returncode,
        "head_stderr": head.stderr.strip(),
        "status_returncode": status.returncode,
        "status_stderr": status.stderr.strip(),
        "working_tree_clean": status.returncode == 0 and not status.stdout.strip(),
        "status_porcelain": status.stdout.splitlines(),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# StatsForecast End-to-End Certification",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{report['decision']}`",
        f"- Formal pass: `{str(report['formal_pass']).lower()}`",
        f"- Expected commit: `{report.get('expected_commit')}`",
        f"- Target-host status: `{report.get('target_status')}`",
        f"- Admission status: `{report.get('admission_status')}`",
        f"- Seed: `{report.get('seed')}`",
        "",
        "## Failures",
        "",
    ]
    failures = report.get("failures") or []
    lines.extend(f"- {failure}" for failure in failures)
    if not failures:
        lines.append("- None")
    lines.extend(
        [
            "",
            "This report certifies runtime evidence only. It does not certify predictive accuracy.",
            "",
        ]
    )
    return "\n".join(lines)


def run_end_to_end_certification(
    repo_root: Path,
    output_root: Path,
    *,
    wheelhouse: Path | None = None,
    run_id: str | None = None,
    prepare_offline: bool = False,
    offline: bool = False,
    expected_commit: str | None = None,
    expected_seed: int = 1,
    horizon: int = 1,
    uv_executable: str = "uv",
    git_context_fn: Callable[[Path], dict[str, Any]] = resolve_git_context,
    target_runner: Callable[..., Any] | None = None,
    admission_inspector: Callable[..., dict[str, Any]] | None = None,
    admission_writer: Callable[..., dict[str, Path]] | None = None,
) -> EndToEndResult:
    if prepare_offline and offline:
        raise ValueError("--prepare-offline and --offline are mutually exclusive")
    if (prepare_offline or offline) and wheelhouse is None:
        raise ValueError("wheelhouse is required for offline preparation or execution")
    if expected_seed < 0:
        raise ValueError("expected_seed must be non-negative")
    if horizon < 1:
        raise ValueError("horizon must be positive")

    run_id = run_id or datetime.now(timezone.utc).strftime(
        "statsforecast-e2e-%Y%m%d-%H%M%S"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    output_dir = output_root / run_id
    output_dir.mkdir(parents=False, exist_ok=False)
    report_path = output_dir / "END_TO_END_REPORT.json"
    admission_dir: Path | None = None
    archive_path: Path | None = None
    failures: list[str] = []
    git_context: dict[str, Any] = {}
    target_status: str | None = None
    admission_status: str | None = None
    admission_decision: str | None = None
    admission_formal_pass = False

    try:
        git_context = git_context_fn(repo_root)
        actual_commit = git_context.get("head")
        normalized_expected = expected_commit.lower() if expected_commit else actual_commit
        if not isinstance(normalized_expected, str) or not _valid_commit(normalized_expected):
            failures.append("expected Git commit is missing or invalid")
        elif actual_commit != normalized_expected:
            failures.append(
                f"Git HEAD mismatch: expected {normalized_expected}, got {actual_commit}"
            )
        if not git_context.get("working_tree_clean"):
            failures.append("working tree is not clean")

        if not failures:
            if target_runner is None:
                from .runtime_lane_target import run_target_host_certification

                target_runner = run_target_host_certification
            target_result = target_runner(
                repo_root,
                output_dir / "target-host",
                run_id="target-host",
                wheelhouse=wheelhouse,
                prepare_offline=prepare_offline,
                offline=offline,
                uv_executable=uv_executable,
                horizon=horizon,
                seed=expected_seed,
            )
            target_status = str(target_result.status)
            archive_path = Path(target_result.archive_path)
            if admission_inspector is None or admission_writer is None:
                from .runtime_lane_admission import (
                    inspect_target_host_archive,
                    write_admission_artifacts,
                )

                admission_inspector = admission_inspector or inspect_target_host_archive
                admission_writer = admission_writer or write_admission_artifacts
            admission_report = admission_inspector(
                archive_path,
                expected_commit=normalized_expected,
                expected_seed=expected_seed,
            )
            admission_status = str(admission_report.get("status"))
            admission_decision = str(admission_report.get("decision"))
            admission_formal_pass = bool(admission_report.get("formal_pass"))
            admission_dir = output_dir / "admission"
            admission_writer(admission_report, admission_dir)
            if target_status != "PASS":
                failures.append(f"target-host status is {target_status}")
            if not admission_formal_pass:
                failures.append(
                    f"admission rejected package: {admission_status}/{admission_decision}"
                )
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
        _write_json(
            output_dir / "END_TO_END_EXCEPTION.json",
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        )

    formal_pass = not failures and target_status == "PASS" and admission_formal_pass
    decision = "RUNTIME_CERTIFIED" if formal_pass else "MERGE_BLOCKED"
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "PASS" if formal_pass else "FAILED",
        "decision": decision,
        "formal_pass": formal_pass,
        "expected_commit": expected_commit.lower() if expected_commit else git_context.get("head"),
        "git_context": git_context,
        "target_status": target_status,
        "target_archive": str(archive_path) if archive_path else None,
        "admission_status": admission_status,
        "admission_decision": admission_decision,
        "admission_dir": str(admission_dir) if admission_dir else None,
        "wheelhouse": str(wheelhouse.resolve()) if wheelhouse else None,
        "prepare_offline": prepare_offline,
        "offline": offline,
        "seed": expected_seed,
        "horizon": horizon,
        "holdout_opened": False,
        "prospective_actual_known": False,
        "predictive_accuracy_certified": False,
        "failures": failures,
        "finished_at_utc": _utc_now(),
    }
    _write_json(report_path, report)
    _atomic_write(
        output_dir / "END_TO_END_REPORT.md",
        _render_markdown(report).encode("utf-8"),
    )
    _write_sums(output_dir)
    return EndToEndResult(
        run_id=run_id,
        output_dir=output_dir,
        report_path=report_path,
        admission_dir=admission_dir,
        archive_path=archive_path,
        expected_commit=report["expected_commit"],
        decision=decision,
        formal_pass=formal_pass,
    )


__all__ = [
    "EndToEndResult",
    "resolve_git_context",
    "run_end_to_end_certification",
]
