"""Run and seal all local HierarchicalForecast promotion gates on one Git commit."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence

from .constants import CertificationError, TARGET_VERSION
from .integrity import (
    atomic_write,
    canonical,
    inside,
    require_directory,
    require_regular_file,
    resolve_requested_root,
    sha_file,
)
from .operator import git_state, run_command
from .quality_gate import EXPECTED_FOCUSED_TESTS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    candidate = PurePosixPath(value)
    if (
        not value
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or candidate.name != value
        or ".." in candidate.parts
        or "\\" in value
    ):
        raise CertificationError(f"unsafe checksum filename: {value!r}")
    return value


def _load_command_json(command: dict[str, object], label: str) -> dict[str, object]:
    stdout_path = require_regular_file(Path(str(command["stdout_path"])), f"{label} stdout")
    try:
        payload = json.loads(stdout_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CertificationError(f"{label} output is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CertificationError(f"{label} output root must be an object")
    return payload


def _parse_checksums(directory: Path) -> dict[str, str]:
    checksum_path = require_regular_file(directory / "SHA256SUMS", "SHA256SUMS")
    rows = checksum_path.read_text(encoding="utf-8").splitlines()
    parsed: dict[str, str] = {}
    for row in rows:
        if not row.strip():
            continue
        try:
            digest, name = row.split("  ", 1)
        except ValueError as exc:
            raise CertificationError(f"invalid SHA256SUMS row: {row!r}") from exc
        name = _safe_name(name)
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise CertificationError(f"invalid SHA-256 digest for {name}")
        if name in parsed:
            raise CertificationError(f"duplicate SHA256SUMS entry: {name}")
        parsed[name] = digest
    return parsed


def verify_evidence_directory(
    directory: Path,
    root: Path,
    report_name: str,
    *,
    identity_field: str,
) -> dict[str, object]:
    directory = inside(directory, root, "evidence directory")
    require_directory(directory, "evidence directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise CertificationError("evidence directory contains a symbolic link")
    regular = {
        entry.name: require_regular_file(entry, f"evidence artifact {entry.name}")
        for entry in entries
        if entry.name != "SHA256SUMS"
    }
    checksums = _parse_checksums(directory)
    if set(checksums) != set(regular):
        raise CertificationError("SHA256SUMS coverage does not match evidence directory")
    for name, digest in checksums.items():
        if sha_file(regular[name]) != digest:
            raise CertificationError(f"SHA256SUMS mismatch: {name}")

    manifest_path = regular.get("ARTIFACT_MANIFEST.json")
    if manifest_path is None:
        raise CertificationError("evidence artifact manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CertificationError(f"invalid evidence artifact manifest: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise CertificationError("evidence artifact manifest has an invalid shape")
    if manifest_path.read_bytes() != canonical(manifest):
        raise CertificationError("evidence artifact manifest is not canonical")
    if manifest.get(identity_field) != directory.name:
        raise CertificationError("evidence artifact manifest identity mismatch")

    expected_manifest_names = set(regular) - {"ARTIFACT_MANIFEST.json"}
    observed: set[str] = set()
    for row in manifest["files"]:
        if not isinstance(row, dict):
            raise CertificationError("invalid evidence artifact manifest row")
        name = _safe_name(str(row.get("path", "")))
        if name in observed or name not in regular:
            raise CertificationError(f"invalid evidence artifact manifest path: {name}")
        observed.add(name)
        path = regular[name]
        if row.get("bytes") != path.stat().st_size or row.get("sha256") != sha_file(path):
            raise CertificationError(f"evidence artifact manifest mismatch: {name}")
    if observed != expected_manifest_names:
        raise CertificationError("evidence artifact manifest coverage mismatch")

    report_path = regular.get(report_name)
    if report_path is None:
        raise CertificationError(f"evidence report is missing: {report_name}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CertificationError(f"invalid persisted evidence report: {exc}") from exc
    if not isinstance(report, dict):
        raise CertificationError("persisted evidence report must be an object")
    if report_path.read_bytes() != canonical(report):
        raise CertificationError("persisted evidence report is not canonical")
    if report.get(identity_field) != directory.name:
        raise CertificationError("persisted evidence report identity mismatch")
    return report


def _verify_git_evidence(payload: dict[str, object], git_sha: str, label: str) -> None:
    if payload.get("expected_git_sha") != git_sha or payload.get("git_commit") != git_sha:
        raise CertificationError(f"{label} Git identity mismatch")
    for field in ("git_preflight", "git_postflight"):
        state = payload.get(field)
        if (
            not isinstance(state, dict)
            or state.get("clean") is not True
            or state.get("commit") != git_sha
        ):
            raise CertificationError(f"{label} {field} evidence mismatch")


def _verify_quality_report(quality: dict[str, object], git_sha: str) -> None:
    if quality.get("status") != "VERIFIED" or quality.get("formal_success") is not True:
        raise CertificationError("formal quality gate did not verify")
    _verify_git_evidence(quality, git_sha, "quality")
    focused = quality.get("focused_junit")
    if (
        not isinstance(focused, dict)
        or focused.get("tests") != EXPECTED_FOCUSED_TESTS
        or focused.get("failures") != 0
        or focused.get("errors") != 0
    ):
        raise CertificationError("quality focused JUnit evidence mismatch")
    full = quality.get("full_junit")
    if not isinstance(full, dict) or full.get("failures") != 0 or full.get("errors") != 0:
        raise CertificationError("quality full-suite JUnit evidence mismatch")


def _verify_target_report(target: dict[str, object], git_sha: str) -> dict[str, object]:
    if target.get("status") != "VERIFIED" or target.get("formal_success") is not True:
        raise CertificationError("formal target certification did not verify")
    _verify_git_evidence(target, git_sha, "target")
    if target.get("installed_version") != TARGET_VERSION:
        raise CertificationError("target installed-version evidence mismatch")
    certification = target.get("certification")
    if not isinstance(certification, dict):
        raise CertificationError("target report lacks certification evidence")
    summary = certification.get("summary")
    if (
        not isinstance(summary, dict)
        or summary.get("expected_cases") != 40
        or summary.get("executed_cases") != 40
        or summary.get("passed_cases") != 40
        or summary.get("failed_cases") != 0
    ):
        raise CertificationError("target 40-case summary mismatch")
    partition = certification.get("method_partition")
    if (
        not isinstance(partition, dict)
        or partition.get("executed_cases") != 24
        or partition.get("rejected_cases") != 16
    ):
        raise CertificationError("target method-partition evidence mismatch")
    return certification


def finalize(
    directory: Path,
    commands: list[dict[str, object]],
    report: dict[str, object],
) -> None:
    atomic_write(directory / "COMMANDS.json", canonical({"commands": commands}))
    atomic_write(directory / "PROMOTION_REPORT.json", canonical(report))
    entries = list(directory.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise CertificationError("promotion directory contains a symbolic link")
    files = sorted(
        [require_regular_file(path, f"promotion artifact {path.name}") for path in entries],
        key=lambda path: path.name,
    )
    manifest = {
        "promotion_run_id": report["promotion_run_id"],
        "git_commit": report.get("git_commit"),
        "files": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha_file(path)}
            for path in files
        ],
    }
    manifest_path = directory / "ARTIFACT_MANIFEST.json"
    atomic_write(manifest_path, canonical(manifest))
    atomic_write(
        directory / "SHA256SUMS",
        "".join(f"{sha_file(path)}  {path.name}\n" for path in [*files, manifest_path]).encode(),
    )


def execute(
    root: Path,
    promotion_root: Path,
    quality_root: Path,
    runtime_root: Path,
    operator_root: Path,
    expected_git_sha: str | None,
    *,
    test_mode: bool = False,
    runner: Callable[[Sequence[str], Path, Path, Path], dict[str, object]] = run_command,
    probe: Callable[[Path], dict[str, object]] = git_state,
) -> tuple[dict[str, object], int]:
    if root.is_symlink():
        raise CertificationError(f"repository root must not be a symbolic link: {root}")
    root = root.resolve()
    promotion_root = resolve_requested_root(root, promotion_root, "promotion root")
    quality_root = resolve_requested_root(root, quality_root, "quality root")
    runtime_root = resolve_requested_root(root, runtime_root, "runtime root")
    operator_root = resolve_requested_root(root, operator_root, "operator root")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"hierarchicalforecast-promotion-{stamp}-{os.getpid()}"
    directory = promotion_root / run_id
    report: dict[str, object] = {
        "promotion_run_id": run_id,
        "status": "FAILED_PREFLIGHT",
        "phase": "preflight",
        "formal_success": False,
        "ready_for_review": False,
        "started_at": utc_now(),
        "finished_at": None,
        "repo_root": str(root),
        "promotion_directory": str(directory),
        "expected_git_sha": expected_git_sha,
        "git_commit": None,
        "git_preflight": None,
        "git_postflight": None,
        "quality": None,
        "target": None,
        "package_verification": None,
        "ci_required": True,
        "error": None,
    }
    commands: list[dict[str, object]] = []
    exit_code = 3
    directory_created = False

    try:
        if not expected_git_sha and not test_mode:
            raise CertificationError("--expected-git-sha is required for the formal promotion gate")
        state = probe(root)
        report["git_preflight"] = state
        if state.get("clean") is not True:
            raise CertificationError("formal promotion gate requires a clean worktree")
        git_sha = str(state.get("commit", ""))
        if not git_sha or expected_git_sha and git_sha != expected_git_sha:
            raise CertificationError("git commit does not match the expected head")
        report["git_commit"] = git_sha
        directory.mkdir(parents=True, exist_ok=False)
        directory_created = True

        def command(name: str, args: list[str]) -> dict[str, object]:
            result = runner(
                args,
                root,
                directory / f"{name}.stdout.log",
                directory / f"{name}.stderr.log",
            )
            commands.append(result)
            return result

        report["phase"] = "quality"
        quality_command = command(
            "quality",
            [
                sys.executable,
                "scripts/run_hierarchicalforecast_quality_gate.py",
                "--repo-root",
                str(root),
                "--evidence-root",
                str(quality_root),
                "--expected-git-sha",
                git_sha,
            ],
        )
        quality = _load_command_json(quality_command, "quality gate")
        report["quality"] = quality
        if quality_command.get("returncode") != 0:
            report["status"] = "FAILED_QUALITY_GATE"
            exit_code = 2 if quality_command.get("returncode") == 2 else 3
            raise CertificationError("formal quality gate command failed")
        _verify_quality_report(quality, git_sha)
        quality_directory = inside(
            Path(str(quality.get("evidence_directory", ""))),
            quality_root,
            "quality evidence directory",
        )
        if quality.get("quality_run_id") != quality_directory.name:
            raise CertificationError("quality report directory identity mismatch")
        persisted_quality = verify_evidence_directory(
            quality_directory,
            quality_root,
            "QUALITY_REPORT.json",
            identity_field="quality_run_id",
        )
        if persisted_quality != quality:
            raise CertificationError("quality stdout and persisted report differ")

        report["phase"] = "target"
        target_command = command(
            "target",
            [
                sys.executable,
                "scripts/run_hierarchicalforecast_target_certification.py",
                "--repo-root",
                str(root),
                "--output-root",
                str(runtime_root),
                "--operator-root",
                str(operator_root),
                "--expected-git-sha",
                git_sha,
            ],
        )
        target = _load_command_json(target_command, "target certification")
        report["target"] = target
        if target_command.get("returncode") != 0:
            report["status"] = "FAILED_TARGET_CERTIFICATION"
            exit_code = 2 if target_command.get("returncode") == 2 else 3
            raise CertificationError("formal target certification command failed")
        certification = _verify_target_report(target, git_sha)
        operator_directory = inside(
            Path(str(target.get("operator_directory", ""))),
            operator_root,
            "operator evidence directory",
        )
        if target.get("operator_run_id") != operator_directory.name:
            raise CertificationError("target report directory identity mismatch")
        persisted_target = verify_evidence_directory(
            operator_directory,
            operator_root,
            "OPERATOR_REPORT.json",
            identity_field="operator_run_id",
        )
        if persisted_target != target:
            raise CertificationError("target stdout and persisted report differ")
        zip_path = inside(
            Path(str(certification.get("zip_path", ""))),
            runtime_root,
            "runtime ZIP",
        )
        require_regular_file(zip_path, "runtime ZIP")

        report["phase"] = "package_verification"
        verifier_command = command(
            "package_verification",
            [
                "uv",
                "run",
                "--locked",
                "loto-hierarchicalforecast-verify-package",
                "--zip",
                str(zip_path),
            ],
        )
        package = _load_command_json(verifier_command, "standalone package verifier")
        report["package_verification"] = package
        if (
            verifier_command.get("returncode") != 0
            or package.get("status") != "VERIFIED"
            or package.get("formal_success") is not True
        ):
            report["status"] = "FAILED_PACKAGE_VERIFICATION"
            exit_code = 2 if verifier_command.get("returncode") == 2 else 3
            raise CertificationError("standalone package verification did not verify")
        package_zip = inside(
            Path(str(package.get("zip_path", ""))),
            runtime_root,
            "verified runtime ZIP",
        )
        if (
            package.get("run_id") != certification.get("run_id")
            or package.get("zip_sha256") != certification.get("zip_sha256")
            or package_zip != zip_path
        ):
            raise CertificationError("standalone package result does not match target evidence")

        report["phase"] = "postflight"
        postflight = probe(root)
        report["git_postflight"] = postflight
        if postflight.get("clean") is not True or postflight.get("commit") != git_sha:
            report["status"] = "FAILED_POSTFLIGHT_GIT_DRIFT"
            raise CertificationError("Git state changed during the promotion gate")

        report["status"] = "LOCAL_GATES_VERIFIED"
        report["phase"] = "complete"
        report["formal_success"] = True
        report["checks"] = {
            "clean_git_preflight": True,
            "quality_gate": True,
            "quality_git_identity": True,
            "quality_focused_count": True,
            "quality_full_suite": True,
            "quality_evidence_hashes": True,
            "target_certification": True,
            "target_git_identity": True,
            "target_exact_version": True,
            "target_40_cases": True,
            "target_method_partition": True,
            "operator_evidence_hashes": True,
            "standalone_package_verification": True,
            "same_runtime_run_id": True,
            "same_zip_sha256": True,
            "clean_git_postflight": True,
            "unchanged_git_commit": True,
            "ci_still_required": True,
        }
        exit_code = 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        if report["status"] == "FAILED_PREFLIGHT":
            report["status"] = {
                "preflight": "FAILED_PREFLIGHT",
                "quality": "FAILED_QUALITY_GATE",
                "target": "FAILED_TARGET_CERTIFICATION",
                "package_verification": "FAILED_PACKAGE_VERIFICATION",
                "postflight": "FAILED_POSTFLIGHT_GIT_DRIFT",
            }.get(str(report["phase"]), "FAILED_PROMOTION_GATE")
        if (
            directory_created
            and exit_code == 3
            and report["status"]
            not in {
                "FAILED_PREFLIGHT",
                "FAILED_POSTFLIGHT_GIT_DRIFT",
            }
        ):
            exit_code = 2
    finally:
        report["finished_at"] = utc_now()
        directory.mkdir(parents=True, exist_ok=True)
        finalize(directory, commands, report)
    return report, exit_code


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, default=Path.cwd())
    result.add_argument(
        "--promotion-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-promotion-runs"),
    )
    result.add_argument(
        "--quality-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-quality-runs"),
    )
    result.add_argument(
        "--runtime-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-runtime"),
    )
    result.add_argument(
        "--operator-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-target-runs"),
    )
    result.add_argument("--expected-git-sha", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report, exit_code = execute(
            args.repo_root,
            args.promotion_root,
            args.quality_root,
            args.runtime_root,
            args.operator_root,
            args.expected_git_sha,
        )
    except Exception as exc:
        report = {
            "status": "FAILED_PROMOTION_BOOTSTRAP",
            "formal_success": False,
            "ready_for_review": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 3
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code
