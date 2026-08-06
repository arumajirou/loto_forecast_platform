from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from loto.timesfm25_campaign.certification_bundle import (
    atomic_write_json,
    atomic_write_text,
    validate_run_id,
    verify_sha256_manifest,
    write_sha256_manifest,
)
from loto.timesfm25_campaign.evidence_archive import (
    EvidenceReviewError,
    inspect_archive,
    safe_extract_archive,
    verify_archive_sidecar,
)

_REQUIRED_FILES = {
    "SHA256SUMS",
    "command.json",
    "environment.json",
    "preflight.json",
    "provider_exit_code.txt",
    "provider_request.json",
    "runtime_certification.json",
    "status.txt",
}
_SUCCESS_STATUSES = {"VERIFIED_CPU", "VERIFIED_GPU", "PARTIALLY_VERIFIED_GPU"}
_OFFLINE = {
    "HF_HUB_OFFLINE": "1",
    "PIP_NO_INDEX": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "UV_OFFLINE": "1",
}


def _json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _common_reasons(
    run_id: str,
    request: dict[str, Any] | None,
    preflight: dict[str, Any] | None,
    certification: dict[str, Any] | None,
    status: str | None,
) -> list[str]:
    if request is None:
        return ["PROVIDER_REQUEST_INVALID"]
    if certification is None:
        return ["RUNTIME_CERTIFICATION_INVALID"]
    reasons = ["PREFLIGHT_INVALID"] if preflight is None else []
    for label, payload in (
        ("REQUEST", request),
        ("PREFLIGHT", preflight),
        ("CERTIFICATION", certification),
    ):
        if payload is not None and payload.get("run_id") != run_id:
            reasons.append(f"{label}_RUN_ID_MISMATCH")
    if request.get("local_files_only") is not True:
        reasons.append("REQUEST_NOT_LOCAL_FILES_ONLY")
    for field in ("backend", "repo_id", "revision"):
        if request.get(field) != certification.get(field):
            reasons.append(f"{field.upper()}_MISMATCH")
    if request.get("device") != certification.get("device_requested"):
        reasons.append("DEVICE_REQUEST_MISMATCH")
    if status != certification.get("runtime_status"):
        reasons.append("STATUS_FILE_MISMATCH")
    if request.get("snapshot_path") != certification.get("snapshot_path"):
        reasons.append("SNAPSHOT_PATH_MISMATCH")
    return reasons


def _preflight_reasons(preflight: dict[str, Any] | None) -> list[str]:
    if preflight is None:
        return ["PREFLIGHT_INVALID"]
    reasons: list[str] = []
    if preflight.get("status") != "PASS":
        reasons.append("PREFLIGHT_STATUS_NOT_PASS")
    if preflight.get("failed_checks") not in ([], ()):
        reasons.append("PREFLIGHT_FAILED_CHECKS_PRESENT")
    checks = preflight.get("checks")
    if not isinstance(checks, list) or not checks:
        reasons.append("PREFLIGHT_CHECKS_MISSING")
    else:
        for check in checks:
            if not isinstance(check, dict):
                reasons.append("PREFLIGHT_CHECK_INVALID")
            elif check.get("required") is True and check.get("status") != "PASS":
                reasons.append(f"PREFLIGHT_REQUIRED_CHECK_FAILED:{check.get('name')}")
    if preflight.get("offline_environment") != _OFFLINE:
        reasons.append("PREFLIGHT_OFFLINE_ENVIRONMENT_MISMATCH")
    return reasons


def _command_reasons(command: dict[str, Any] | None) -> list[str]:
    if command is None:
        return ["COMMAND_EVIDENCE_INVALID"]
    argv = command.get("command")
    if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
        return ["COMMAND_ARGV_INVALID"]
    reasons = [f"COMMAND_MISSING:{flag}" for flag in ("--locked", "--offline") if flag not in argv]
    if not any(value.endswith("scripts/run_timesfm25_provider.py") for value in argv):
        reasons.append("COMMAND_PROVIDER_PATH_MISSING")
    if command.get("offline_environment") != _OFFLINE:
        reasons.append("COMMAND_OFFLINE_ENVIRONMENT_MISMATCH")
    return reasons


def _environment_reasons(value: dict[str, Any] | None) -> tuple[list[str], str | None, bool]:
    if value is None or not isinstance(value.get("commands"), dict):
        return ["ENVIRONMENT_COMMANDS_INVALID"], None, True
    commands = value["commands"]
    head = commands.get("git_head")
    status = commands.get("git_status")
    reasons: list[str] = []
    head_value: str | None = None
    dirty = True
    if not isinstance(head, dict) or head.get("returncode") != 0:
        reasons.append("GIT_HEAD_CAPTURE_FAILED")
    else:
        candidate = str(head.get("stdout", "")).strip()
        if len(candidate) == 40 and all(char in "0123456789abcdef" for char in candidate):
            head_value = candidate
        else:
            reasons.append("GIT_HEAD_INVALID")
    if not isinstance(status, dict) or status.get("returncode") != 0:
        reasons.append("GIT_STATUS_CAPTURE_FAILED")
    else:
        dirty = bool(str(status.get("stdout", "")).strip())
        if dirty:
            reasons.append("GIT_WORKTREE_DIRTY")
    return reasons, head_value, dirty


def _provider_exit_reasons(path: Path, certification: dict[str, Any] | None) -> list[str]:
    try:
        value = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return ["PROVIDER_EXIT_FILE_INVALID"]
    if certification is None or value != certification.get("provider_exit_code"):
        return ["PROVIDER_EXIT_FILE_MISMATCH"]
    return []


def _strict_gpu_reasons(certification: dict[str, Any], bundle_dir: Path) -> list[str]:
    expected = {
        "device_requested": "cuda",
        "gpu_certification_status": "PASS",
        "provider_exit_code": 0,
        "timed_out": False,
        "provider_response_valid": True,
        "external_pid_match": True,
        "cpu_fallback": False,
    }
    reasons = [
        f"STRICT_GPU_{field.upper()}_FAILED"
        for field, value in expected.items()
        if certification.get(field) != value
    ]
    for field in ("model_parameter_device", "mean_output_device", "quantile_output_device"):
        value = certification.get(field)
        if not isinstance(value, str) or not value.lower().startswith("cuda"):
            reasons.append(f"STRICT_GPU_{field.upper()}_FAILED")
    peak = certification.get("vram_peak_bytes")
    if not isinstance(peak, int) or isinstance(peak, bool) or peak <= 0:
        reasons.append("STRICT_GPU_VRAM_PEAK_FAILED")
    samples = bundle_dir / "nvidia_process_samples.csv"
    if not samples.is_file() or samples.stat().st_size == 0:
        reasons.append("STRICT_GPU_NVIDIA_SAMPLES_MISSING")
    return reasons


def review_extracted_bundle(bundle_dir: Path, archive_sha256: str) -> dict[str, Any]:
    run_id = validate_run_id(bundle_dir.name)
    reasons = [
        f"REQUIRED_FILE_MISSING:{name}"
        for name in sorted(_REQUIRED_FILES)
        if not (bundle_dir / name).is_file()
    ]
    manifest_ok, manifest_failures = verify_sha256_manifest(bundle_dir)
    if not manifest_ok:
        reasons.append("INTERNAL_SHA256_FAILED")
        reasons.extend(f"INTERNAL_SHA256:{value}" for value in manifest_failures)

    request = _json(bundle_dir / "provider_request.json")
    preflight = _json(bundle_dir / "preflight.json")
    certification = _json(bundle_dir / "runtime_certification.json")
    response = _json(bundle_dir / "provider_response.json")
    command = _json(bundle_dir / "command.json")
    environment = _json(bundle_dir / "environment.json")
    status_path = bundle_dir / "status.txt"
    status = status_path.read_text(encoding="utf-8").strip() if status_path.is_file() else None
    reasons.extend(_common_reasons(run_id, request, preflight, certification, status))
    git_reasons, git_head, git_dirty = _environment_reasons(environment)
    reasons.extend(git_reasons)
    reasons.extend(_command_reasons(command))
    reasons.extend(_provider_exit_reasons(bundle_dir / "provider_exit_code.txt", certification))

    runtime_status = certification.get("runtime_status") if certification else None
    if runtime_status in _SUCCESS_STATUSES:
        reasons.extend(_preflight_reasons(preflight))
        if response is None or response.get("status") != "OK":
            reasons.append("SUCCESS_WITHOUT_VALID_PROVIDER_RESPONSE")

    formal_status = "REJECTED"
    exit_code = 1
    if not reasons and certification is not None:
        if runtime_status == "VERIFIED_GPU":
            reasons.extend(_strict_gpu_reasons(certification, bundle_dir))
            if not reasons:
                formal_status, exit_code = "FORMAL_GPU_CERTIFIED", 0
        elif runtime_status == "VERIFIED_CPU":
            if request is None or request.get("device") != "cpu":
                reasons.append("VERIFIED_CPU_DEVICE_MISMATCH")
            elif certification.get("provider_exit_code") != 0:
                reasons.append("VERIFIED_CPU_PROVIDER_EXIT_FAILED")
            elif certification.get("cpu_fallback") is True:
                reasons.append("VERIFIED_CPU_MARKED_AS_FALLBACK")
            else:
                formal_status, exit_code = "FORMAL_CPU_CERTIFIED", 0
        elif runtime_status == "PARTIALLY_VERIFIED_GPU":
            formal_status, exit_code = "PARTIALLY_VERIFIED_GPU", 2
        elif runtime_status == "FAILED":
            reasons.append("RUNTIME_STATUS_FAILED")
        else:
            reasons.append("RUNTIME_STATUS_UNKNOWN")

    review_status = "PASS" if exit_code == 0 else "PARTIAL" if exit_code == 2 else "FAIL"
    samples = bundle_dir / "nvidia_process_samples.csv"
    return {
        "schema_version": 1,
        "run_id": run_id,
        "archive_sha256": archive_sha256,
        "review_status": review_status,
        "formal_status": formal_status,
        "exit_code": exit_code,
        "runtime_status": runtime_status,
        "reasons": reasons,
        "internal_manifest_ok": manifest_ok,
        "internal_manifest_failures": list(manifest_failures),
        "backend": certification.get("backend") if certification else None,
        "repo_id": certification.get("repo_id") if certification else None,
        "revision": certification.get("revision") if certification else None,
        "device_requested": certification.get("device_requested") if certification else None,
        "gpu_certification_status": (
            certification.get("gpu_certification_status") if certification else None
        ),
        "vram_peak_bytes": certification.get("vram_peak_bytes") if certification else None,
        "external_pid_match": certification.get("external_pid_match") if certification else None,
        "cpu_fallback": certification.get("cpu_fallback") if certification else None,
        "git_head": git_head,
        "git_dirty": git_dirty,
        "offline_command_ok": not _command_reasons(command),
        "nvidia_samples_present": samples.is_file() and samples.stat().st_size > 0,
    }


def render_review_markdown(report: dict[str, Any]) -> str:
    reasons = report["reasons"] or ["NONE"]
    lines = [
        "# TimesFM 2.5 Evidence Review",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Review status: `{report['review_status']}`",
        f"- Formal status: `{report['formal_status']}`",
        f"- Runtime status: `{report['runtime_status']}`",
        f"- Archive SHA-256: `{report['archive_sha256']}`",
        f"- Internal SHA-256: `{'PASS' if report['internal_manifest_ok'] else 'FAIL'}`",
        "",
        "## Reasons",
        "",
        *(f"- `{reason}`" for reason in reasons),
        "",
        "This review never promotes `PARTIALLY_VERIFIED_GPU` to formal GPU certification.",
        "",
    ]
    return "\n".join(lines)


def review_archive(
    archive_path: Path,
    sidecar_path: Path,
    output_root: Path,
    *,
    expected_run_id: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    archive = archive_path.resolve()
    sidecar = sidecar_path.resolve()
    output_root = output_root.resolve()
    digest = verify_archive_sidecar(archive, sidecar)
    inspection = inspect_archive(archive)
    run_id = inspection["run_id"]
    if expected_run_id is not None and validate_run_id(expected_run_id) != run_id:
        raise EvidenceReviewError("archive Run ID does not match expected Run ID")

    review_id = f"{run_id}-{digest[:12]}"
    final_dir = output_root / review_id
    if final_dir.exists():
        raise FileExistsError(f"immutable review directory already exists: {final_dir}")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / f".{review_id}.{os.getpid()}.tmp"
    if temporary.exists():
        raise FileExistsError(f"temporary review directory already exists: {temporary}")

    try:
        bundle_dir = safe_extract_archive(archive, temporary / "bundle", run_id)
        report = review_extracted_bundle(bundle_dir, digest)
        report.update(
            archive_path=str(archive),
            sidecar_path=str(sidecar),
            archive_member_count=inspection["member_count"],
            archive_uncompressed_bytes=inspection["total_uncompressed_bytes"],
        )
        atomic_write_json(temporary / "EVIDENCE_REVIEW.json", report)
        atomic_write_text(temporary / "EVIDENCE_REVIEW.md", render_review_markdown(report))
        atomic_write_text(temporary / "ARCHIVE_SHA256.txt", f"{digest}  {archive.name}\n")
        write_sha256_manifest(temporary, manifest_name="REVIEW_SHA256SUMS")
        ok, failures = verify_sha256_manifest(temporary, manifest_name="REVIEW_SHA256SUMS")
        if not ok:
            raise RuntimeError(f"outer review sealing failed: {failures}")
        os.replace(temporary, final_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return final_dir, report
