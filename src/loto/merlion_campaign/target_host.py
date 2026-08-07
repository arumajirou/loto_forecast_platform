from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Sequence

from loto.adapters.merlion.adapter import MerlionProviderAdapter
from loto.merlion_campaign.certification import CertificationResult, certify_core_model
from loto.merlion_campaign.protocol import (
    Operation,
    ProviderRequest,
    SeriesPayload,
    TimeSemantics,
)

CoreModel = Literal["Arima", "ETS", "MSES"]
CORE_MODELS: tuple[CoreModel, ...] = ("Arima", "ETS", "MSES")
EXPECTED_PACKAGE = "salesforce-merlion"
EXPECTED_VERSION = "2.0.4"
EXPECTED_UPSTREAM_REVISION = "39507642dc3d7b8d04232e34e9f36b372cf4912d"


class TargetHostError(RuntimeError):
    """Raised when target-host evidence is invalid or cannot be published."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_message(exc: BaseException) -> str:
    message = str(exc).replace("\n", " ").replace("\r", " ")
    message = re.sub(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@", r"\1<redacted>@", message)
    message = re.sub(
        r"(?i)(token|password|secret|api[_-]?key)=([^&\s]+)",
        r"\1=<redacted>",
        message,
    )
    return message[:2000]


def _require_hex(value: str, length: int, label: str) -> None:
    if len(value) != length or any(character not in "0123456789abcdef" for character in value):
        raise TargetHostError(f"{label} must be {length} lowercase hexadecimal characters")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _series_payload() -> SeriesPayload:
    values = [float(10 + index * 0.15 + ((index % 7) - 3) * 0.4) for index in range(56)]
    return SeriesPayload(name="position-1", values=values, draw_numbers=list(range(1, 57)))


def _request(model_name: CoreModel) -> ProviderRequest:
    return ProviderRequest(
        request_id=f"merlion-core-{model_name.lower()}",
        operation=Operation.TRAIN_SAVE,
        model_name=model_name,
        series=_series_payload(),
        time_semantics=TimeSemantics.DRAW_SEQUENCE,
        horizon=3,
        artifact_subdir=f"models/{model_name.lower()}",
    )


def _validate_identity(evidence: dict[str, Any]) -> None:
    required = {
        "package_name": EXPECTED_PACKAGE,
        "installed_version": EXPECTED_VERSION,
        "version_match": True,
        "upstream_revision": EXPECTED_UPSTREAM_REVISION,
        "upstream_archived": True,
    }
    for key, expected in required.items():
        if evidence.get(key) != expected:
            raise TargetHostError(
                f"identity mismatch for {key}: expected {expected!r}, got {evidence.get(key)!r}"
            )


def _validate_discovery(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    rows = evidence.get("models")
    if not isinstance(rows, list) or not rows:
        raise TargetHostError("discovery response has no model rows")
    names = {row.get("model_name") for row in rows if isinstance(row, dict)}
    missing = sorted(set(CORE_MODELS) - names)
    if missing:
        raise TargetHostError(f"core aliases missing from discovery: {missing}")
    return [row for row in rows if isinstance(row, dict)]


def _manifest_payload(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise TargetHostError(f"symbolic link is not allowed: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}:
            continue
        files.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return {
        "schema_version": "merlion-target-host-manifest-v1",
        "files": files,
    }


def _finalize_bundle(staging: Path, output_dir: Path) -> dict[str, Any]:
    manifest = _manifest_payload(staging)
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    _write_json(staging / "ARTIFACT_MANIFEST.json", manifest)
    files = sorted(path for path in staging.rglob("*") if path.is_file())
    sums = "".join(
        f"{_sha256_file(path)}  {path.relative_to(staging).as_posix()}\n"
        for path in files
        if path.name != "SHA256SUMS"
    )
    (staging / "SHA256SUMS").write_text(sums, encoding="utf-8")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise TargetHostError(f"output already exists: {output_dir}")
    os.replace(staging, output_dir)
    return verify_target_host_run(output_dir)


def run_target_host_certification(
    command: Sequence[str],
    output_dir: Path,
    *,
    expected_git_sha: str,
    lock_sha256: str,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    _require_hex(expected_git_sha, 40, "expected_git_sha")
    _require_hex(lock_sha256, 64, "lock_sha256")
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise TargetHostError(f"output already exists: {output_dir}")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.partial-", dir=output_dir.parent)
    )
    phase = "initialization"
    status = "BLOCKED"
    identity_evidence: dict[str, Any] = {}
    discovery_evidence: dict[str, Any] = {}
    model_reports: list[dict[str, Any]] = []
    try:
        work_root = staging / "provider-work"
        adapter = MerlionProviderAdapter(command, timeout_seconds=timeout_seconds)

        phase = "identity"
        identity = adapter.run(
            ProviderRequest(request_id="merlion-core-identity", operation=Operation.IDENTITY),
            work_root,
        )
        identity_evidence = dict(identity.evidence)
        _validate_identity(identity_evidence)
        _write_json(staging / "IDENTITY.json", identity_evidence)

        phase = "discovery"
        discovery = adapter.run(
            ProviderRequest(request_id="merlion-core-discovery", operation=Operation.DISCOVER),
            work_root,
        )
        discovery_evidence = dict(discovery.evidence)
        rows = _validate_discovery(discovery_evidence)
        _write_json(staging / "DISCOVERY.json", discovery_evidence)

        phase = "model_lifecycle"
        for model_name in CORE_MODELS:
            result: CertificationResult = certify_core_model(
                command,
                _request(model_name),
                work_root,
                timeout_seconds=timeout_seconds,
            )
            report = dict(result.report)
            report["model_name"] = model_name
            model_reports.append(report)
            if result.status != "RUNTIME_VERIFIED":
                raise TargetHostError(f"{model_name} certification status is {result.status}")

        _write_json(staging / "MODEL_RUNTIME_MATRIX.json", model_reports)
        status = "RUNTIME_CERTIFIED"
        report = {
            "schema_version": "merlion-target-host-report-v1",
            "status": status,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "git_sha": expected_git_sha,
            "lock_sha256": lock_sha256,
            "provider_command_recorded": False,
            "package_name": identity_evidence.get("package_name"),
            "installed_version": identity_evidence.get("installed_version"),
            "upstream_revision": identity_evidence.get("upstream_revision"),
            "factory_alias_count": len(rows),
            "core_models": list(CORE_MODELS),
            "runtime_verified_models": [row["model_name"] for row in model_reports],
            "runtime_verified_count": len(model_reports),
            "device": "cpu",
            "gpu_not_applicable": True,
            "automatic_promotion": False,
            "holdout_opened": False,
            "prospective_opened": False,
        }
        report["report_sha256"] = _canonical_sha256(report)
        _write_json(staging / "VERIFICATION_REPORT.json", report)
    except Exception as exc:
        status = "BLOCKED"
        failure = {
            "schema_version": "merlion-target-host-failure-v1",
            "status": "BLOCKED",
            "phase": phase,
            "exception_type": type(exc).__name__,
            "message": _safe_message(exc),
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "git_sha": expected_git_sha,
            "lock_sha256": lock_sha256,
        }
        _write_json(staging / "FAILURE.json", failure)
        report = {
            "schema_version": "merlion-target-host-report-v1",
            "status": "BLOCKED",
            "generated_at_utc": failure["generated_at_utc"],
            "git_sha": expected_git_sha,
            "lock_sha256": lock_sha256,
            "failed_phase": phase,
            "runtime_verified_count": len(model_reports),
            "automatic_promotion": False,
            "holdout_opened": False,
            "prospective_opened": False,
        }
        report["report_sha256"] = _canonical_sha256(report)
        _write_json(staging / "VERIFICATION_REPORT.json", report)
    verification = _finalize_bundle(staging, output_dir)
    verification["source_status"] = status
    return verification


def _parse_sums(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if (
            not separator
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or relative in entries
        ):
            raise TargetHostError("invalid SHA256SUMS entry")
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise TargetHostError("unsafe SHA256SUMS path")
        entries[relative] = digest
    return entries


def verify_target_host_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise TargetHostError(f"run directory does not exist: {run_dir}")
    for path in run_dir.rglob("*"):
        if path.is_symlink():
            raise TargetHostError(f"symbolic link is not allowed: {path}")
    sums_path = run_dir / "SHA256SUMS"
    manifest_path = run_dir / "ARTIFACT_MANIFEST.json"
    report_path = run_dir / "VERIFICATION_REPORT.json"
    if not sums_path.is_file() or not manifest_path.is_file() or not report_path.is_file():
        raise TargetHostError("required evidence file is missing")
    sums = _parse_sums(sums_path)
    actual_files = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(sums) != actual_files:
        raise TargetHostError("SHA256SUMS inventory does not match run files")
    for relative, expected in sums.items():
        if _sha256_file(run_dir / relative) != expected:
            raise TargetHostError(f"SHA-256 mismatch: {relative}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_copy = dict(manifest)
    manifest_sha = manifest_copy.pop("manifest_sha256", None)
    if manifest_sha != _canonical_sha256(manifest_copy):
        raise TargetHostError("artifact manifest self-hash mismatch")
    rows = manifest.get("files", [])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise TargetHostError("artifact manifest rows are invalid")
    listed = {row.get("path") for row in rows}
    if len(listed) != len(rows):
        raise TargetHostError("artifact manifest contains duplicate paths")
    expected_listed = actual_files - {"ARTIFACT_MANIFEST.json"}
    if listed != expected_listed:
        raise TargetHostError("artifact manifest inventory mismatch")
    for row in rows:
        relative = row["path"]
        path = run_dir / relative
        if row.get("size_bytes") != path.stat().st_size:
            raise TargetHostError(f"artifact size mismatch: {relative}")
        if row.get("sha256") != _sha256_file(path):
            raise TargetHostError(f"artifact manifest SHA-256 mismatch: {relative}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report_copy = dict(report)
    report_sha = report_copy.pop("report_sha256", None)
    if report_sha != _canonical_sha256(report_copy):
        raise TargetHostError("verification report self-hash mismatch")
    source_status = report.get("status")
    if source_status == "RUNTIME_CERTIFIED":
        matrix_path = run_dir / "MODEL_RUNTIME_MATRIX.json"
        if not matrix_path.is_file() or (run_dir / "FAILURE.json").exists():
            raise TargetHostError("certified run has invalid success evidence set")
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        names = [row.get("model_name") for row in matrix if isinstance(row, dict)]
        statuses = [row.get("status") for row in matrix if isinstance(row, dict)]
        if names != list(CORE_MODELS) or statuses != ["RUNTIME_VERIFIED"] * len(CORE_MODELS):
            raise TargetHostError("certified model matrix is incomplete or out of order")
    elif source_status == "BLOCKED":
        if not (run_dir / "FAILURE.json").is_file():
            raise TargetHostError("blocked run is missing FAILURE.json")
    else:
        raise TargetHostError(f"unsupported source status: {source_status!r}")
    return {
        "status": "VERIFIED",
        "source_status": source_status,
        "file_count": len(actual_files) + 1,
        "sha256_entries": len(sums),
        "git_sha": report.get("git_sha"),
        "lock_sha256": report.get("lock_sha256"),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or verify Merlion core certification")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--provider-command-json", required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--expected-git-sha", required=True)
    run.add_argument("--lock-sha256", required=True)
    run.add_argument("--timeout-seconds", type=float, default=300.0)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--run", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "verify":
        print(json.dumps(verify_target_host_run(args.run), sort_keys=True))
        return 0
    command = json.loads(args.provider_command_json)
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise TargetHostError("provider command must be a JSON string array")
    result = run_target_host_certification(
        command,
        args.output,
        expected_git_sha=args.expected_git_sha,
        lock_sha256=args.lock_sha256,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("source_status") == "RUNTIME_CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
