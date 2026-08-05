"""Formal target-machine orchestration and immutable operator evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from .constants import CertificationError, TARGET_VERSION
from .integrity import (
    atomic_write,
    canonical,
    require_regular_file,
    resolve_requested_root,
    sha_file,
)
from .package_verification import verify_formal


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(
    command: Sequence[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, object]:
    started_at = utc_now()
    started = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    atomic_write(stdout_path, completed.stdout.encode())
    atomic_write(stderr_path, completed.stderr.encode())
    return {
        "command": list(command),
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_seconds": time.perf_counter() - started,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def git_state(root: Path) -> dict[str, object]:
    def capture(args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise CertificationError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    status = capture(["status", "--porcelain=v1", "--untracked-files=all"])
    return {
        "commit": capture(["rev-parse", "HEAD"]),
        "branch": capture(["rev-parse", "--abbrev-ref", "HEAD"]),
        "clean": not bool(status),
        "status_porcelain": status.splitlines() if status else [],
    }


def finalize(directory: Path, commands: list[dict[str, object]], report: dict[str, object]) -> None:
    atomic_write(directory / "COMMANDS.json", canonical({"commands": commands}))
    atomic_write(directory / "OPERATOR_REPORT.json", canonical(report))
    entries = list(directory.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise CertificationError("operator directory contains a symbolic link")
    files = sorted(
        [require_regular_file(path, f"operator artifact {path.name}") for path in entries],
        key=lambda path: path.name,
    )
    manifest = {
        "operator_run_id": report["operator_run_id"],
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
    output_root: Path,
    operator_root: Path,
    expected_git_sha: str | None = None,
    skip_sync: bool = False,
    *,
    test_mode: bool = False,
    runner: Callable[[Sequence[str], Path, Path, Path], dict[str, object]] = run_command,
    probe: Callable[[Path], dict[str, object]] = git_state,
) -> tuple[dict[str, object], int]:
    if root.is_symlink():
        raise CertificationError(f"repository root must not be a symbolic link: {root}")
    root = root.resolve()
    output_root = resolve_requested_root(root, output_root, "output root")
    operator_root = resolve_requested_root(root, operator_root, "operator root")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"hierarchicalforecast-target-{stamp}-{os.getpid()}"
    directory = operator_root / run_id
    report: dict[str, object] = {
        "operator_run_id": run_id,
        "status": "FAILED_PREFLIGHT",
        "phase": "preflight",
        "formal_success": False,
        "started_at": utc_now(),
        "finished_at": None,
        "repo_root": str(root),
        "output_root": str(output_root),
        "operator_directory": str(directory),
        "expected_version": TARGET_VERSION,
        "expected_git_sha": expected_git_sha,
        "git_preflight": None,
        "git_postflight": None,
        "certification": None,
        "error": None,
    }
    commands: list[dict[str, object]] = []
    exit_code = 3
    try:
        if not expected_git_sha and not test_mode:
            raise CertificationError("--expected-git-sha is required for formal certification")
        if skip_sync and not test_mode:
            raise CertificationError("sync may only be skipped by isolated tests")
        state = probe(root)
        report["git_preflight"] = state
        if state.get("clean") is not True:
            raise CertificationError("formal certification requires a clean worktree")
        git_sha = str(state.get("commit", ""))
        if not git_sha or expected_git_sha and git_sha != expected_git_sha:
            raise CertificationError("git commit does not match the expected head")
        directory.mkdir(parents=True, exist_ok=False)
        output_root.mkdir(parents=True, exist_ok=True)

        def command(name: str, args: list[str]) -> dict[str, object]:
            result = runner(
                args,
                root,
                directory / f"{name}.stdout.log",
                directory / f"{name}.stderr.log",
            )
            commands.append(result)
            return result

        if not skip_sync:
            report["phase"] = "sync"
            if command("sync", ["uv", "sync", "--extra", "full", "--locked"])["returncode"]:
                report["status"] = "FAILED_SYNC"
                raise CertificationError("uv sync failed")
        report["phase"] = "dependency"
        version = command(
            "version",
            [
                "uv",
                "run",
                "--locked",
                "python",
                "-c",
                "from importlib.metadata import version; print(version('hierarchicalforecast'))",
            ],
        )
        installed = Path(str(version["stdout_path"])).read_text(encoding="utf-8").strip()
        report["installed_version"] = installed
        if version["returncode"] or installed != TARGET_VERSION:
            report["status"] = "FAILED_VERSION_MISMATCH"
            exit_code = 2
            raise CertificationError(f"installed version is {installed!r}")
        report["phase"] = "certification"
        certification = command(
            "certification",
            [
                "uv",
                "run",
                "--locked",
                "loto-hierarchicalforecast-certify",
                "--output-root",
                str(output_root),
                "--expected-version",
                TARGET_VERSION,
            ],
        )
        payload = _parse_certification_output(certification)
        if certification["returncode"]:
            nested = payload.get("certification")
            report["status"] = str(
                nested.get("status") if isinstance(nested, dict) else payload.get("status")
            )
            report["certification"] = payload
            exit_code = 2 if certification["returncode"] == 2 else 3
            raise CertificationError("formal certification command failed")
        report["phase"] = "verification"
        report["certification"] = verify_formal(
            payload,
            output_root,
            git_sha,
            repo_root=None if test_mode else root,
        )
        report["phase"] = "postflight"
        postflight = probe(root)
        report["git_postflight"] = postflight
        if postflight.get("clean") is not True or postflight.get("commit") != git_sha:
            report["status"] = "FAILED_POSTFLIGHT_GIT_DRIFT"
            raise CertificationError("Git state changed during formal certification")
        report["status"] = "VERIFIED"
        report["phase"] = "complete"
        report["formal_success"] = True
        report["checks"] = {
            "clean_git_preflight": True,
            "clean_git_postflight": True,
            "unchanged_git_commit": True,
            "locked_sync": not skip_sync,
            "exact_version": True,
            "forty_cases": True,
            "runtime_hashes": True,
            "runtime_no_symlinks": True,
            "source_hashes": True,
            "zip_and_sidecar": True,
        }
        exit_code = 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        if report["status"] == "FAILED_PREFLIGHT":
            report["status"] = {
                "preflight": "FAILED_PREFLIGHT",
                "sync": "FAILED_SYNC",
                "dependency": "FAILED_VERSION_PROBE",
                "certification": "FAILED_CERTIFICATION_OUTPUT",
                "verification": "FAILED_OPERATOR_VERIFICATION",
                "postflight": "FAILED_POSTFLIGHT_GIT_DRIFT",
            }.get(str(report["phase"]), "FAILED_OPERATOR")
    finally:
        report["finished_at"] = utc_now()
        directory.mkdir(parents=True, exist_ok=True)
        finalize(directory, commands, report)
    return report, exit_code


def _parse_certification_output(command: dict[str, object]) -> dict[str, object]:
    try:
        payload = json.loads(Path(str(command["stdout_path"])).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CertificationError(f"certification output is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CertificationError("certification output root is not an object")
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, default=Path.cwd())
    result.add_argument(
        "--output-root",
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
            args.output_root,
            args.operator_root,
            expected_git_sha=args.expected_git_sha,
        )
    except Exception as exc:
        report = {
            "status": "FAILED_OPERATOR_BOOTSTRAP",
            "formal_success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 3
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code
