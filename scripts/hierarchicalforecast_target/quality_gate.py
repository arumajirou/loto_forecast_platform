"""Run the formal local quality gate and seal its evidence."""

from __future__ import annotations

import argparse
import json
import os
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from .constants import CertificationError
from .dependency_contract import verify_dependency_contract
from .integrity import (
    atomic_write,
    canonical,
    require_regular_file,
    resolve_requested_root,
    sha_file,
)
from .operator import git_state, run_command

FOCUSED_TESTS = (
    "tests/test_reconciliation.py",
    "tests/test_reconciliation_upstream_matrix.py",
    "tests/test_reconciliation_runtime_certification.py",
    "tests/test_reconciliation_console_script.py",
    "tests/test_reconciliation_package_certification.py",
    "tests/test_reconciliation_package_verifier.py",
    "tests/test_reconciliation_target_machine_certification.py",
    "tests/test_reconciliation_target_operator.py",
    "tests/test_reconciliation_promotion_gate.py",
    "tests/test_reconciliation_quality_gate.py",
)
EXPECTED_FOCUSED_TESTS = 95
RUFF_SCOPE = ("src", "scripts", "tests")
MYPY_SCOPE = (
    "src/loto/reconciliation/hierarchy.py",
    "src/loto/reconciliation/runtime_certification.py",
    "src/loto/reconciliation/package_certification.py",
    "src/loto/reconciliation/portable_package_certification.py",
    "src/loto/reconciliation/package_verifier.py",
    "scripts/hierarchicalforecast_target",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def parse_junit(path: Path, *, expected_tests: int | None = None) -> dict[str, int]:
    require_regular_file(path, "JUnit XML")
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise CertificationError(f"invalid JUnit XML {path}: {exc}") from exc

    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise CertificationError(f"JUnit XML has no test suites: {path}")

    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            try:
                totals[key] += int(suite.attrib.get(key, "0"))
            except ValueError as exc:
                raise CertificationError(f"invalid JUnit {key} count: {path}") from exc

    if totals["failures"] or totals["errors"]:
        raise CertificationError(f"JUnit reports failed tests: {totals}")
    if expected_tests is not None and totals["tests"] != expected_tests:
        raise CertificationError(
            f"focused test count mismatch: expected={expected_tests} actual={totals['tests']}"
        )
    return totals


def finalize(directory: Path, commands: list[dict[str, object]], report: dict[str, object]) -> None:
    atomic_write(directory / "COMMANDS.json", canonical({"commands": commands}))
    atomic_write(directory / "QUALITY_REPORT.json", canonical(report))
    entries = list(directory.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise CertificationError("quality evidence directory contains a symbolic link")
    files = sorted(
        [require_regular_file(path, f"quality artifact {path.name}") for path in entries],
        key=lambda path: path.name,
    )
    manifest = {
        "quality_run_id": report["quality_run_id"],
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
    evidence_root: Path,
    expected_git_sha: str | None,
    *,
    skip_sync: bool = False,
    skip_full_suite: bool = False,
    test_mode: bool = False,
    runner: Callable[[Sequence[str], Path, Path, Path], dict[str, object]] = run_command,
    probe: Callable[[Path], dict[str, object]] = git_state,
) -> tuple[dict[str, object], int]:
    if root.is_symlink():
        raise CertificationError(f"repository root must not be a symbolic link: {root}")
    root = root.resolve()
    evidence_root = resolve_requested_root(root, evidence_root, "quality evidence root")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"hierarchicalforecast-quality-{stamp}-{os.getpid()}"
    directory = evidence_root / run_id
    report: dict[str, object] = {
        "quality_run_id": run_id,
        "status": "FAILED_PREFLIGHT",
        "phase": "preflight",
        "formal_success": False,
        "started_at": utc_now(),
        "finished_at": None,
        "repo_root": str(root),
        "evidence_directory": str(directory),
        "expected_git_sha": expected_git_sha,
        "git_commit": None,
        "git_preflight": None,
        "git_postflight": None,
        "dependency_contract": None,
        "focused_junit": None,
        "full_junit": None,
        "error": None,
    }
    commands: list[dict[str, object]] = []
    exit_code = 3
    directory_created = False

    try:
        if not expected_git_sha and not test_mode:
            raise CertificationError("--expected-git-sha is required for the formal quality gate")
        if (skip_sync or skip_full_suite) and not test_mode:
            raise CertificationError("quality-gate phases may only be skipped by isolated tests")

        state = probe(root)
        report["git_preflight"] = state
        if state.get("clean") is not True:
            raise CertificationError("formal quality gate requires a clean worktree")
        git_sha = str(state.get("commit", ""))
        if not git_sha or expected_git_sha and git_sha != expected_git_sha:
            raise CertificationError("git commit does not match the expected head")
        report["git_commit"] = git_sha

        directory.mkdir(parents=True, exist_ok=False)
        directory_created = True

        report["phase"] = "dependency_contract"
        if test_mode:
            report["dependency_contract"] = {
                "status": "SKIPPED_TEST_MODE",
                "formal_success": False,
            }
        else:
            report["dependency_contract"] = verify_dependency_contract(root)

        def command(name: str, args: list[str], status: str) -> dict[str, object]:
            report["phase"] = name
            result = runner(
                args,
                root,
                directory / f"{name}.stdout.log",
                directory / f"{name}.stderr.log",
            )
            commands.append(result)
            if result.get("returncode") != 0:
                report["status"] = status
                raise CertificationError(f"quality command failed: {name}")
            return result

        if not skip_sync:
            command(
                "sync",
                ["uv", "sync", "--extra", "dev", "--extra", "full", "--locked"],
                "FAILED_SYNC",
            )

        command(
            "pip_check",
            ["uv", "pip", "check"],
            "FAILED_PIP_CHECK",
        )
        command(
            "ruff_format",
            [
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "ruff",
                "format",
                "--check",
                *RUFF_SCOPE,
            ],
            "FAILED_RUFF_FORMAT",
        )
        command(
            "ruff_lint",
            ["uv", "run", "--locked", "python", "-m", "ruff", "check", *RUFF_SCOPE],
            "FAILED_RUFF_LINT",
        )
        command(
            "compileall",
            ["uv", "run", "--locked", "python", "-m", "compileall", "-q", *RUFF_SCOPE],
            "FAILED_COMPILEALL",
        )
        command(
            "mypy",
            ["uv", "run", "--locked", "python", "-m", "mypy", *MYPY_SCOPE],
            "FAILED_MYPY",
        )

        focused_xml = directory / "focused.junit.xml"
        command(
            "focused_pytest",
            [
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "pytest",
                "-q",
                f"--junitxml={focused_xml}",
                *FOCUSED_TESTS,
            ],
            "FAILED_FOCUSED_TESTS",
        )
        report["focused_junit"] = parse_junit(
            focused_xml,
            expected_tests=EXPECTED_FOCUSED_TESTS,
        )

        if not skip_full_suite:
            full_xml = directory / "full.junit.xml"
            command(
                "full_pytest",
                [
                    "uv",
                    "run",
                    "--locked",
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                    f"--junitxml={full_xml}",
                ],
                "FAILED_FULL_TESTS",
            )
            report["full_junit"] = parse_junit(full_xml)

        report["phase"] = "postflight"
        postflight = probe(root)
        report["git_postflight"] = postflight
        if postflight.get("clean") is not True or postflight.get("commit") != git_sha:
            report["status"] = "FAILED_POSTFLIGHT_GIT_DRIFT"
            raise CertificationError("Git state changed during the quality gate")

        report["status"] = "VERIFIED"
        report["phase"] = "complete"
        report["formal_success"] = True
        report["checks"] = {
            "clean_git_preflight": True,
            "clean_git_postflight": True,
            "unchanged_git_commit": True,
            "dependency_contract": not test_mode,
            "locked_sync": not skip_sync,
            "pip_check": True,
            "ruff_format": True,
            "ruff_lint": True,
            "compileall": True,
            "mypy": True,
            "focused_95": True,
            "full_pytest": not skip_full_suite,
        }
        exit_code = 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        if report["status"] == "FAILED_PREFLIGHT":
            report["status"] = {
                "preflight": "FAILED_PREFLIGHT",
                "dependency_contract": "FAILED_DEPENDENCY_CONTRACT",
                "sync": "FAILED_SYNC",
                "pip_check": "FAILED_PIP_CHECK",
                "ruff_format": "FAILED_RUFF_FORMAT",
                "ruff_lint": "FAILED_RUFF_LINT",
                "compileall": "FAILED_COMPILEALL",
                "mypy": "FAILED_MYPY",
                "focused_pytest": "FAILED_FOCUSED_TESTS",
                "full_pytest": "FAILED_FULL_TESTS",
                "postflight": "FAILED_POSTFLIGHT_GIT_DRIFT",
            }.get(str(report["phase"]), "FAILED_QUALITY_GATE")
        exit_code = 2 if str(report["status"]).startswith("FAILED_") and directory_created else 3
        if report["status"] in {"FAILED_PREFLIGHT", "FAILED_POSTFLIGHT_GIT_DRIFT"}:
            exit_code = 3
    finally:
        report["finished_at"] = utc_now()
        directory.mkdir(parents=True, exist_ok=True)
        finalize(directory, commands, report)
    return report, exit_code


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, default=Path.cwd())
    result.add_argument(
        "--evidence-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-quality-runs"),
    )
    result.add_argument("--expected-git-sha", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report, exit_code = execute(
            args.repo_root,
            args.evidence_root,
            args.expected_git_sha,
        )
    except Exception as exc:
        report = {
            "status": "FAILED_QUALITY_BOOTSTRAP",
            "formal_success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 3
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code
