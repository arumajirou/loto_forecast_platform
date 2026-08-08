from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ID = "thuml/sundial-base-128m"
REVISION = "3212e42564493f520593e5414af4367fc4b49226"
EXPECTED_SAMPLE_COUNTS = (1, 3, 20, 50, 100)
EXPECTED_CASES = (
    "cpu-smoke-ns001",
    "cuda-ns001",
    "cuda-ns003",
    "cuda-ns020",
    "cuda-ns050",
    "cuda-ns100",
    "cuda-replay-a",
    "cuda-replay-b",
)
RUN_ID_PATTERN = re.compile(r"^sundial-v2-\d{8}-\d{6}$")
CHECKSUM_PATTERN = re.compile(r"^([0-9a-f]{64})  (.+)$")


class EvidenceError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_relative(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise EvidenceError(f"unsafe checksum path: {raw}")
    return path


def verify_checksums(run_dir: Path) -> dict[str, str]:
    checksum_path = run_dir / "SHA256SUMS"
    if not checksum_path.is_file():
        raise EvidenceError("SHA256SUMS is missing")
    expected: dict[str, str] = {}
    for line_number, line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        match = CHECKSUM_PATTERN.fullmatch(line)
        if match is None:
            raise EvidenceError(f"invalid SHA256SUMS line {line_number}")
        digest, raw_path = match.groups()
        relative = safe_relative(raw_path)
        key = relative.as_posix()
        if key in expected:
            raise EvidenceError(f"duplicate checksum path: {key}")
        target = run_dir / relative
        if target.is_symlink() or not target.is_file():
            raise EvidenceError(f"checksummed file is missing or symlinked: {key}")
        actual = sha256(target)
        if actual != digest:
            raise EvidenceError(f"SHA-256 mismatch: {key}")
        expected[key] = digest
    actual_files = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(expected) != actual_files:
        missing = sorted(actual_files - set(expected))
        extra = sorted(set(expected) - actual_files)
        raise EvidenceError(f"checksum coverage mismatch: missing={missing}, extra={extra}")
    return expected


def flatten(value: Any) -> list[float]:
    if isinstance(value, list):
        result: list[float] = []
        for item in value:
            result.extend(flatten(item))
        return result
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [float(value)]
    raise EvidenceError("prediction payload contains a non-numeric value")


def compare_samples(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    a = flatten(left.get("samples"))
    b = flatten(right.get("samples"))
    if len(a) != len(b):
        return {"classification": "SHAPE_MISMATCH", "passed": False}
    exact = a == b
    close = all(math.isclose(x, y, rel_tol=1e-6, abs_tol=1e-7) for x, y in zip(a, b, strict=True))
    return {
        "classification": "EXACT" if exact else "NUMERIC_CLOSE" if close else "DIVERGENT",
        "passed": exact or close,
        "sample_count": len(a),
        "maximum_absolute_difference": max(
            (abs(x - y) for x, y in zip(a, b, strict=True)), default=0.0
        ),
    }


def verify_case(run_dir: Path, case: dict[str, Any], seed: int) -> list[str]:
    reasons: list[str] = []
    name = str(case.get("name", ""))
    case_dir = run_dir / "cases" / name
    device = "cpu" if name == "cpu-smoke-ns001" else "cuda"
    if not case_dir.is_dir():
        return ["CASE_DIRECTORY_MISSING"]
    try:
        request = load_json(case_dir / "request.json")
        response = load_json(case_dir / "response.json")
        monitor = load_json(case_dir / "gpu-monitor.json")
    except EvidenceError as exc:
        return [f"CASE_FILE_INVALID:{exc}"]
    num_samples = int(case.get("num_samples", -1))
    pid = int(case.get("pid", -1))
    if case.get("device") != device:
        reasons.append("CASE_DEVICE_MISMATCH")
    if case.get("seed") != seed or request.get("seed") != seed:
        reasons.append("SEED_MISMATCH")
    if case.get("passed") is not True or case.get("reasons") != []:
        reasons.append("CASE_NOT_PASSED")
    if case.get("return_code") != 0 or case.get("timed_out") is not False:
        reasons.append("CASE_PROCESS_FAILURE")
    if request.get("repo_id") != REPO_ID or request.get("revision") != REVISION:
        reasons.append("REQUEST_IDENTITY_MISMATCH")
    if request.get("device") != device or request.get("num_samples") != num_samples:
        reasons.append("REQUEST_SHAPE_MISMATCH")
    if request.get("prediction_length") != 1 or request.get("local_files_only") is not True:
        reasons.append("REQUEST_CONTRACT_MISMATCH")
    if response.get("status") != "OK" or response.get("provider_version") != 2:
        reasons.append("RESPONSE_STATUS_MISMATCH")
    if response.get("repo_id") != REPO_ID or response.get("revision") != REVISION:
        reasons.append("RESPONSE_IDENTITY_MISMATCH")
    if response.get("samples_shape") != [7, num_samples, 1]:
        reasons.append("RESPONSE_SAMPLE_SHAPE_MISMATCH")
    try:
        samples = flatten(response.get("samples"))
        points = flatten(response.get("predictions"))
        if len(samples) != 7 * num_samples or not all(map(math.isfinite, samples)):
            reasons.append("RESPONSE_SAMPLES_INVALID")
        if len(points) != 7 or not all(map(math.isfinite, points)):
            reasons.append("RESPONSE_POINTS_INVALID")
    except EvidenceError:
        reasons.append("RESPONSE_NON_NUMERIC")
    gpu = response.get("gpu_evidence")
    if not isinstance(gpu, dict):
        reasons.append("GPU_EVIDENCE_MISSING")
    else:
        if gpu.get("cpu_fallback") is not False:
            reasons.append("CPU_FALLBACK")
        if gpu.get("execution_device") != device:
            reasons.append("EXECUTION_DEVICE_MISMATCH")
        if device == "cpu":
            if gpu.get("gpu_used") is not False:
                reasons.append("CPU_SMOKE_USED_GPU")
        else:
            if gpu.get("gpu_used") is not True or gpu.get("gpu_pid") != pid:
                reasons.append("GPU_PROCESS_MISMATCH")
            if int(gpu.get("peak_vram_bytes") or 0) <= 0:
                reasons.append("INTERNAL_VRAM_MISSING")
            if case.get("external_gpu_pid_seen") is not True:
                reasons.append("EXTERNAL_GPU_PID_MISSING")
            if int(case.get("external_peak_vram_mib") or 0) <= 0:
                reasons.append("EXTERNAL_VRAM_MISSING")
    if monitor.get("pid") != pid:
        reasons.append("MONITOR_PID_MISMATCH")
    if device == "cuda":
        if monitor.get("external_seen") is not True:
            reasons.append("MONITOR_GPU_PID_MISSING")
        if int(monitor.get("external_peak_mib") or 0) <= 0:
            reasons.append("MONITOR_VRAM_MISSING")
    if case.get("request_sha256") != sha256(case_dir / "request.json"):
        reasons.append("REQUEST_HASH_MISMATCH")
    if case.get("response_sha256") != sha256(case_dir / "response.json"):
        reasons.append("RESPONSE_HASH_MISMATCH")
    return reasons


def verify_repository_hashes(root: Path, environment: dict[str, Any]) -> list[str]:
    checks = {
        "runner_sha256": root / "scripts" / "run_sundial_provider.py",
        "harness_sha256": root / "scripts" / "certify_sundial_provider_v2.py",
        "sundial_lock_sha256": root / "environments" / "sundial" / "uv.lock",
        "remote_code_review_sha256": (
            root / "audit" / "tsfm-runtime" / "sundial-base" / "remote-code-review.json"
        ),
    }
    reasons: list[str] = []
    for key, path in checks.items():
        if not path.is_file() or environment.get(key) != sha256(path):
            reasons.append(f"{key.upper()}_MISMATCH")
    return reasons


def missing_status_report(
    run_dir: Path,
    *,
    expected_commit: str | None,
    expected_branch: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "verified_at_utc": utc_now(),
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "status": "FAIL",
        "reasons": ["STATUS_FILE_MISSING"],
        "case_results": {},
        "recomputed_reproducibility": None,
        "checksum_entry_count": 0,
        "expected_commit": expected_commit,
        "expected_branch": expected_branch,
    }


def verify_run(
    run_dir: Path,
    *,
    repo_root: Path | None,
    expected_commit: str | None,
    expected_branch: str | None,
) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise EvidenceError(f"invalid run directory: {run_dir}")
    status_path = run_dir / "status.txt"
    if not status_path.is_file() or status_path.is_symlink():
        return missing_status_report(
            run_dir,
            expected_commit=expected_commit,
            expected_branch=expected_branch,
        )
    checksum_entries = verify_checksums(run_dir)
    summary = load_json(run_dir / "certification-summary.json")
    environment = load_json(run_dir / "environment.json")
    reproducibility = load_json(run_dir / "reproducibility.json")
    manifest = load_json(run_dir / "ARTIFACT_MANIFEST.json")
    reasons: list[str] = []
    run_id = str(summary.get("run_id", ""))
    if not RUN_ID_PATTERN.fullmatch(run_id) or run_dir.name != run_id:
        reasons.append("RUN_ID_MISMATCH")
    for document in (environment, manifest):
        if document.get("run_id") != run_id:
            reasons.append("DOCUMENT_RUN_ID_MISMATCH")
    if summary.get("schema_version") != 1:
        reasons.append("SCHEMA_VERSION_MISMATCH")
    if summary.get("repo_id") != REPO_ID or summary.get("revision") != REVISION:
        reasons.append("SUMMARY_IDENTITY_MISMATCH")
    if summary.get("status") != "PASS" or summary.get("formal_gpu_certification") is not True:
        reasons.append("SUMMARY_NOT_CERTIFIED")
    if summary.get("cpu_fallback_allowed") is not False:
        reasons.append("CPU_FALLBACK_POLICY_MISMATCH")
    if tuple(summary.get("sample_counts", [])) != EXPECTED_SAMPLE_COUNTS:
        reasons.append("SAMPLE_COUNT_MATRIX_MISMATCH")
    seed = int(summary.get("seed", -1))
    cases = summary.get("cases")
    if not isinstance(cases, list):
        reasons.append("CASES_MISSING")
        cases = []
    case_names = [str(case.get("name", "")) for case in cases if isinstance(case, dict)]
    if tuple(case_names) != EXPECTED_CASES or len(set(case_names)) != len(case_names):
        reasons.append("CASE_MATRIX_MISMATCH")
    case_results: dict[str, list[str]] = {}
    for case in cases:
        if isinstance(case, dict):
            result = verify_case(run_dir, case, seed)
            case_results[str(case.get("name", ""))] = result
            reasons.extend(f"{case.get('name')}:{reason}" for reason in result)
    replay = compare_samples(
        load_json(run_dir / "cases" / "cuda-replay-a" / "response.json"),
        load_json(run_dir / "cases" / "cuda-replay-b" / "response.json"),
    )
    if reproducibility.get("passed") is not True:
        reasons.append("REPRODUCIBILITY_NOT_PASSED")
    if reproducibility.get("classification") not in {"EXACT", "NUMERIC_CLOSE"}:
        reasons.append("REPRODUCIBILITY_CLASSIFICATION_INVALID")
    if replay != reproducibility:
        reasons.append("REPRODUCIBILITY_RECOMPUTE_MISMATCH")
    try:
        status_lines = status_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        status_lines = []
        reasons.append("STATUS_FILE_UNREADABLE")
    if not status_lines or status_lines[0] != "SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS":
        reasons.append("STATUS_FILE_MISMATCH")
    required_files = set(manifest.get("required_files", []))
    required_manifest_files = {
        "environment.json",
        "certification-summary.json",
        "reproducibility.json",
        "SHA256SUMS",
    }
    if not required_manifest_files.issubset(required_files):
        reasons.append("MANIFEST_REQUIRED_FILES_MISMATCH")
    if tuple(manifest.get("case_directories", [])) != EXPECTED_CASES:
        reasons.append("MANIFEST_CASE_MATRIX_MISMATCH")
    if environment.get("git_status_porcelain") not in {None, ""}:
        reasons.append("WORKTREE_NOT_CLEAN_AT_START")
    if expected_commit and environment.get("git_commit") != expected_commit:
        reasons.append("GIT_COMMIT_MISMATCH")
    if expected_branch and environment.get("git_branch") != expected_branch:
        reasons.append("GIT_BRANCH_MISMATCH")
    if repo_root is not None:
        reasons.extend(verify_repository_hashes(repo_root.resolve(), environment))
    return {
        "schema_version": 1,
        "verified_at_utc": utc_now(),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "case_results": case_results,
        "recomputed_reproducibility": replay,
        "checksum_entry_count": len(checksum_entries),
        "expected_commit": expected_commit,
        "expected_branch": expected_branch,
    }


def render_markdown(report: dict[str, Any]) -> str:
    reasons = report["reasons"] or ["NONE"]
    return "\n".join(
        [
            "# Sundial provider v2 evidence verification",
            "",
            f"- Status: `{report['status']}`",
            f"- Run ID: `{report['run_id']}`",
            f"- Verified at: `{report['verified_at_utc']}`",
            f"- Checksum entries: `{report['checksum_entry_count']}`",
            "",
            "## Reasons",
            "",
            *[f"- `{reason}`" for reason in reasons],
            "",
        ]
    )


def create_archive(
    run_dir: Path,
    verification_dir: Path,
    archive_path: Path,
    *,
    semantic_reports: tuple[Path, ...] = (),
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_root, prefix in ((run_dir, "run"), (verification_dir, "verification")):
            for path in sorted(source_root.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{prefix}/{path.relative_to(source_root).as_posix()}")
        for path in semantic_reports:
            archive.write(path, f"semantic/{path.name}")
    (archive_path.with_suffix(archive_path.suffix + ".sha256")).write_text(
        f"{sha256(archive_path)}  {archive_path.name}\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and package Sundial provider v2 evidence")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-branch", default="feat/sundial-probabilistic-provider-v2")
    parser.add_argument("--semantic-report", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/sundial-provider-v2-verified"),
    )
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    semantic_reports: tuple[Path, ...] = ()
    if args.semantic_report is not None:
        semantic_report = args.semantic_report.expanduser().resolve()
        if semantic_report.is_symlink() or not semantic_report.is_file():
            raise EvidenceError(f"invalid semantic report: {semantic_report}")
        semantic_reports = (semantic_report,)
    report = verify_run(
        args.run_dir,
        repo_root=args.repo_root,
        expected_commit=args.expected_commit,
        expected_branch=args.expected_branch,
    )
    report["semantic_reports"] = [
        {"path": str(path), "sha256": sha256(path)} for path in semantic_reports
    ]
    run_id = str(report["run_id"] or args.run_dir.name)
    output = args.output_root.expanduser().resolve() / run_id
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    write_json(output / "VERIFICATION_REPORT.json", report)
    markdown = render_markdown(report)
    (output / "VERIFICATION_REPORT.md").write_text(markdown, encoding="utf-8")
    (output / "PR_COMMENT.md").write_text(markdown, encoding="utf-8")
    if args.archive and report["status"] == "PASS":
        archive = output.parent / f"{run_id}-evidence.zip"
        create_archive(
            args.run_dir.resolve(),
            output,
            archive,
            semantic_reports=semantic_reports,
        )
        report["archive"] = str(archive)
        report["archive_sha256"] = sha256(archive)
        write_json(output / "VERIFICATION_REPORT.json", report)
    print(f"SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION={report['status']}")
    print(f"VERIFICATION_DIR={output}")
    if report.get("archive"):
        print(f"ARCHIVE={report['archive']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        print(f"SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION=BLOCKED\nREASON={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
