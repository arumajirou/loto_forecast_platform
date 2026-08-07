from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class TriageResult:
    output_dir: Path
    classification_path: Path
    remediation_path: Path
    status: str
    primary_classification: str
    progress_percent: int


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
    _atomic_write(
        path,
        (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8"),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_sums(root: Path) -> Path:
    checksum_path = root / "SHA256SUMS"
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and path != checksum_path:
            rows.append(
                f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}"
            )
    _atomic_write(checksum_path, ("\n".join(rows) + "\n").encode("utf-8"))
    return checksum_path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _find_unique(root: Path, filename: str) -> tuple[Path | None, list[str]]:
    matches = sorted(path for path in root.rglob(filename) if path.is_file())
    if len(matches) == 1:
        return matches[0], []
    if not matches:
        return None, [f"missing {filename}"]
    relative = [path.relative_to(root).as_posix() for path in matches]
    return None, [f"ambiguous {filename}: {relative}"]


def _flatten_text(values: Iterable[Any]) -> str:
    return " ".join(str(value) for value in values if value is not None).lower()


def _classify(
    report: dict[str, Any],
    exception: dict[str, Any] | None,
    admission: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
    verification: dict[str, Any] | None,
    model_matrix: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    failures = list(report.get("failures") or [])
    text = _flatten_text(
        [
            *failures,
            exception.get("type") if exception else None,
            exception.get("message") if exception else None,
            admission.get("failures") if admission else None,
        ]
    )
    findings: list[dict[str, Any]] = []

    def add(code: str, severity: str, evidence: list[str]) -> None:
        if not any(item["code"] == code for item in findings):
            findings.append(
                {"code": code, "severity": severity, "evidence": evidence}
            )

    if report.get("formal_pass") is True and report.get("decision") == "RUNTIME_CERTIFIED":
        add("NO_FAILURE", "INFO", ["end-to-end formal pass is true"])
        return findings

    git_context = report.get("git_context") or {}
    if (
        not git_context.get("working_tree_clean", True)
        or "working tree" in text
        or "git head mismatch" in text
        or "expected git commit" in text
    ):
        add("GIT_PREFLIGHT", "BLOCKING", failures or ["Git preflight failed"])

    if any(
        token in text
        for token in (
            "mutually exclusive",
            "wheelhouse is required",
            "horizon must",
            "seed must",
            "run directory",
        )
    ):
        add("CONFIGURATION", "BLOCKING", failures)

    if any(
        token in text
        for token in (
            "network",
            "dns",
            "pypi",
            "pythonhosted",
            "uv lock",
            "pip download",
            "wheelhouse",
            "dependency",
            "connection",
            "resolve",
        )
    ):
        add("DEPENDENCY_OR_NETWORK", "BLOCKING", failures)

    if any(
        token in text
        for token in (
            "sha-256",
            "checksum",
            "archive",
            "zip",
            "tamper",
            "unsafe member",
            "digest",
        )
    ):
        add("EVIDENCE_INTEGRITY", "BLOCKING", failures)

    if report.get("admission_status") == "REJECTED" or (
        admission and admission.get("formal_pass") is False
    ):
        evidence = list(admission.get("failures") or []) if admission else failures
        add("ADMISSION_REJECTED", "BLOCKING", evidence)

    failed_models: list[str] = []
    if model_matrix:
        failed_models = [
            str(row.get("model_name"))
            for row in model_matrix
            if row.get("status")
            not in {"VERIFIED", "EXPECTED_NEGATIVE_PASS"}
        ]
    if failed_models or (
        runtime and runtime.get("certification_returncode") not in {None, 0}
    ) or (verification and verification.get("formal_pass") is False):
        add(
            "MODEL_RUNTIME",
            "BLOCKING",
            [f"failed models: {failed_models}"] if failed_models else failures,
        )

    if report.get("target_status") not in {None, "PASS"} and not findings:
        add("TARGET_HOST_RUNTIME", "BLOCKING", failures)

    if not findings:
        add("UNKNOWN", "BLOCKING", failures or ["No recognized failure signature"])
    return findings


def _progress_percent(
    report: dict[str, Any],
    admission: dict[str, Any] | None,
    verification: dict[str, Any] | None,
) -> int:
    if report.get("formal_pass") is True:
        return 100
    git_context = report.get("git_context") or {}
    if not git_context.get("working_tree_clean", False):
        return 10
    if report.get("target_status") is None:
        return 20
    if report.get("target_archive") is None:
        return 45
    if verification is None:
        return 60
    if verification.get("formal_pass") is not True:
        return 75
    if admission is None:
        return 85
    if admission.get("formal_pass") is not True:
        return 90
    return 95


def _remediation_steps(
    classifications: list[dict[str, Any]],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    codes = {item["code"] for item in classifications}
    commit = report.get("expected_commit") or "$(git rev-parse HEAD)"
    seed = int(report.get("seed", 1))
    horizon = int(report.get("horizon", 1))
    steps: list[dict[str, Any]] = []

    def add(step_id: str, title: str, commands: list[str]) -> None:
        steps.append(
            {
                "step_id": step_id,
                "title": title,
                "commands": commands,
            }
        )

    if "NO_FAILURE" in codes:
        add(
            "VERIFY_SUMS",
            "Re-verify final evidence before review",
            ["sha256sum -c SHA256SUMS"],
        )
        return steps
    if "GIT_PREFLIGHT" in codes:
        add(
            "CLEAN_GIT",
            "Inspect and resolve worktree or commit mismatch",
            [
                "git status --short",
                "git rev-parse HEAD",
                f"test \"$(git rev-parse HEAD)\" = \"{commit}\"",
            ],
        )
    if "CONFIGURATION" in codes:
        add(
            "VALIDATE_ARGS",
            "Use one execution mode and valid fixed parameters",
            [
                "Choose exactly one of --prepare-offline or --offline",
                f"Use --seed {seed} --horizon {horizon}",
            ],
        )
    if "DEPENDENCY_OR_NETWORK" in codes:
        add(
            "CHECK_NETWORK",
            "Verify package host resolution and create a new wheelhouse",
            [
                "getent hosts pypi.org files.pythonhosted.org",
                "uv --version",
                "python3.13 --version",
            ],
        )
    if "MODEL_RUNTIME" in codes:
        add(
            "INSPECT_MODELS",
            "Inspect failed model rows and certification logs",
            [
                "find . -name MODEL_RUNTIME_MATRIX.json -o -name certification.stderr.log",
                "grep -R \"EXECUTION_FAILED\\|CONSTRUCTION_FAILED\" .",
            ],
        )
    if "EVIDENCE_INTEGRITY" in codes:
        add(
            "VERIFY_EVIDENCE",
            "Re-check archive and checksums without modifying evidence",
            [
                "find . -name SHA256SUMS -print",
                "sha256sum -c SHA256SUMS",
            ],
        )
    if "ADMISSION_REJECTED" in codes:
        add(
            "INSPECT_ADMISSION",
            "Review admission failures before rerunning",
            ["cat admission/ADMISSION_REPORT.md"],
        )
    add(
        "RERUN_E2E",
        "Run a fresh end-to-end certification in a new directory",
        [
            "PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_lane.py "
            "end-to-end --output-root artifacts/statsforecast-end-to-end-rerun "
            "--wheelhouse artifacts/statsforecast-offline-bundle-rerun "
            f"--prepare-offline --expected-commit {commit} "
            f"--horizon {horizon} --seed {seed}"
        ],
    )
    return steps


def _render_markdown(
    classification: dict[str, Any],
    remediation: dict[str, Any],
) -> str:
    lines = [
        "# StatsForecast Failure Triage",
        "",
        f"- Status: `{classification['status']}`",
        f"- Primary classification: `{classification['primary_classification']}`",
        f"- Progress: `{classification['progress_percent']}%`",
        f"- Merge decision: `{classification['merge_decision']}`",
        "",
        "## Findings",
        "",
    ]
    for finding in classification["classifications"]:
        lines.append(f"- `{finding['code']}` ({finding['severity']})")
    lines.extend(["", "## Remediation", ""])
    for step in remediation["steps"]:
        lines.append(f"### {step['step_id']}: {step['title']}")
        lines.append("")
        for command in step["commands"]:
            lines.append(f"- `{command}`")
        lines.append("")
    return "\n".join(lines)


def triage_end_to_end_run(
    end_to_end_dir: Path,
    output_dir: Path,
) -> TriageResult:
    report_path = end_to_end_dir / "END_TO_END_REPORT.json"
    if not report_path.is_file() or report_path.is_symlink():
        raise FileNotFoundError(f"missing END_TO_END_REPORT.json: {end_to_end_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    report = _load_json(report_path)

    exception_path = end_to_end_dir / "END_TO_END_EXCEPTION.json"
    exception = _load_json(exception_path) if exception_path.is_file() else None

    diagnostics: list[str] = []
    admission_path, issues = _find_unique(end_to_end_dir, "ADMISSION_REPORT.json")
    diagnostics.extend(issues)
    runtime_path, issues = _find_unique(end_to_end_dir, "RUNTIME_LANE_REPORT.json")
    diagnostics.extend(issues)
    verification_path, issues = _find_unique(end_to_end_dir, "VERIFICATION_REPORT.json")
    diagnostics.extend(issues)
    matrix_path, issues = _find_unique(end_to_end_dir, "MODEL_RUNTIME_MATRIX.json")
    diagnostics.extend(issues)

    admission = _load_json(admission_path) if admission_path else None
    runtime = _load_json(runtime_path) if runtime_path else None
    verification = _load_json(verification_path) if verification_path else None
    matrix_payload = json.loads(matrix_path.read_text(encoding="utf-8")) if matrix_path else None
    model_matrix = matrix_payload if isinstance(matrix_payload, list) else None

    classifications = _classify(
        report,
        exception,
        admission,
        runtime,
        verification,
        model_matrix,
    )
    primary = classifications[0]["code"]
    progress = _progress_percent(report, admission, verification)
    formal_pass = report.get("formal_pass") is True and primary == "NO_FAILURE"
    classification = {
        "schema_version": 1,
        "status": "NO_FAILURE" if formal_pass else "FAILURE_CLASSIFIED",
        "primary_classification": primary,
        "progress_percent": progress,
        "merge_decision": "RUNTIME_CERTIFIED" if formal_pass else "MERGE_BLOCKED",
        "source_end_to_end_dir": str(end_to_end_dir.resolve()),
        "source_report_sha256": _sha256_file(report_path),
        "classifications": classifications,
        "diagnostics": diagnostics,
        "created_at_utc": _utc_now(),
    }
    remediation = {
        "schema_version": 1,
        "status": "NOT_REQUIRED" if formal_pass else "REMEDIATION_REQUIRED",
        "primary_classification": primary,
        "steps": _remediation_steps(classifications, report),
        "created_at_utc": _utc_now(),
    }
    classification_path = output_dir / "FAILURE_CLASSIFICATION.json"
    remediation_path = output_dir / "REMEDIATION_PLAN.json"
    _write_json(classification_path, classification)
    _write_json(remediation_path, remediation)
    _atomic_write(
        output_dir / "REMEDIATION_PLAN.md",
        _render_markdown(classification, remediation).encode("utf-8"),
    )
    _write_sums(output_dir)
    return TriageResult(
        output_dir=output_dir,
        classification_path=classification_path,
        remediation_path=remediation_path,
        status=classification["status"],
        primary_classification=primary,
        progress_percent=progress,
    )


__all__ = ["TriageResult", "triage_end_to_end_run"]
