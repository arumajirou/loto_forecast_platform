# ruff: noqa: E402
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from hierarchicalforecast_target import quality_gate


def _junit(path: Path, tests: int, failures: int = 0, errors: int = 0, skipped: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<testsuites><testsuite tests="{tests}" failures="{failures}" '
            f'errors="{errors}" skipped="{skipped}"/></testsuites>'
        ),
        encoding="utf-8",
    )


def _result(command: Sequence[str], cwd: Path, stdout_path: Path, stderr_path: Path, code: int = 0):
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    return {
        "command": list(command),
        "cwd": str(cwd),
        "returncode": code,
        "started_at": "s",
        "finished_at": "f",
        "duration_seconds": 0.1,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _clean_probe(commit: str = "a" * 40):
    return {
        "commit": commit,
        "branch": "test",
        "clean": True,
        "status_porcelain": [],
    }


def _write_dependency_contract(repo: Path, version: str = "1.5.1") -> None:
    (repo / "pyproject.toml").write_text(
        """
[project]
name = "loto-forecast-platform"
requires-python = ">=3.11,<3.14"

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-cov>=5",
  "ruff>=0.9",
  "mypy>=1.13",
  "pydantic[email]>=2.8,<3",
]
full = ["hierarchicalforecast>=1.0"]
""".lstrip(),
        encoding="utf-8",
    )
    (repo / "uv.lock").write_text(
        f"""
version = 1
revision = 3
requires-python = ">=3.11, <3.14"

[[package]]
name = "hierarchicalforecast"
version = "{version}"

[[package]]
name = "loto-forecast-platform"

[package.optional-dependencies]
full = [{{ name = "hierarchicalforecast" }}]
""".lstrip(),
        encoding="utf-8",
    )


def test_parse_junit_requires_exact_focused_count(tmp_path: Path) -> None:
    path = tmp_path / "focused.xml"
    _junit(path, quality_gate.EXPECTED_FOCUSED_TESTS - 1)
    with pytest.raises(quality_gate.CertificationError, match="count mismatch"):
        quality_gate.parse_junit(path, expected_tests=quality_gate.EXPECTED_FOCUSED_TESTS)


def test_parse_junit_rejects_failures(tmp_path: Path) -> None:
    path = tmp_path / "focused.xml"
    _junit(path, quality_gate.EXPECTED_FOCUSED_TESTS, failures=1)
    with pytest.raises(quality_gate.CertificationError, match="failed tests"):
        quality_gate.parse_junit(path, expected_tests=quality_gate.EXPECTED_FOCUSED_TESTS)


def test_quality_gate_success_runs_full_suite_last(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_dependency_contract(repo)
    contract = quality_gate.verify_dependency_contract(repo)
    assert contract["locked_versions"] == ["1.5.1"]
    assert contract["declaration_exact"] is False
    _write_dependency_contract(repo, version="1.5.0")
    with pytest.raises(quality_gate.CertificationError, match="must resolve only"):
        quality_gate.verify_dependency_contract(repo)
    _write_dependency_contract(repo)

    commands: list[list[str]] = []

    def runner(command, cwd, stdout_path, stderr_path):
        commands.append(list(command))
        for argument in command:
            if isinstance(argument, str) and argument.startswith("--junitxml="):
                xml_path = Path(argument.split("=", 1)[1])
                count = quality_gate.EXPECTED_FOCUSED_TESTS if "focused" in xml_path.name else 120
                _junit(xml_path, count, skipped=2)
        return _result(command, cwd, stdout_path, stderr_path)

    probes = iter([_clean_probe(), _clean_probe()])
    report, code = quality_gate.execute(
        repo,
        Path("artifacts/quality"),
        "a" * 40,
        skip_sync=True,
        test_mode=True,
        runner=runner,
        probe=lambda _: next(probes),
    )

    assert code == 0
    assert report["status"] == "VERIFIED"
    assert report["dependency_contract"]["status"] == "SKIPPED_TEST_MODE"
    assert report["focused_junit"]["tests"] == quality_gate.EXPECTED_FOCUSED_TESTS
    assert report["full_junit"]["tests"] == 120
    assert commands[-1][5] == "pytest"
    assert Path(report["evidence_directory"], "SHA256SUMS").is_file()


def test_focused_failure_stops_before_full_suite(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    names: list[str] = []

    def runner(command, cwd, stdout_path, stderr_path):
        name = stdout_path.name.removesuffix(".stdout.log")
        names.append(name)
        code = 1 if name == "focused_pytest" else 0
        return _result(command, cwd, stdout_path, stderr_path, code)

    report, code = quality_gate.execute(
        repo,
        Path("quality"),
        "a" * 40,
        skip_sync=True,
        test_mode=True,
        runner=runner,
        probe=lambda _: _clean_probe(),
    )

    assert code == 2
    assert report["status"] == "FAILED_FOCUSED_TESTS"
    assert "full_pytest" not in names


def test_wrong_focused_count_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def runner(command, cwd, stdout_path, stderr_path):
        for argument in command:
            if isinstance(argument, str) and argument.startswith("--junitxml="):
                _junit(
                    Path(argument.split("=", 1)[1]),
                    quality_gate.EXPECTED_FOCUSED_TESTS - 1,
                )
        return _result(command, cwd, stdout_path, stderr_path)

    report, code = quality_gate.execute(
        repo,
        Path("quality"),
        "a" * 40,
        skip_sync=True,
        skip_full_suite=True,
        test_mode=True,
        runner=runner,
        probe=lambda _: _clean_probe(),
    )

    assert code == 2
    assert report["status"] == "FAILED_FOCUSED_TESTS"
    assert "count mismatch" in report["error"]


def test_postflight_git_drift_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def runner(command, cwd, stdout_path, stderr_path):
        for argument in command:
            if isinstance(argument, str) and argument.startswith("--junitxml="):
                _junit(
                    Path(argument.split("=", 1)[1]),
                    quality_gate.EXPECTED_FOCUSED_TESTS,
                )
        return _result(command, cwd, stdout_path, stderr_path)

    probes = iter([_clean_probe(), _clean_probe("b" * 40)])
    report, code = quality_gate.execute(
        repo,
        Path("quality"),
        "a" * 40,
        skip_sync=True,
        skip_full_suite=True,
        test_mode=True,
        runner=runner,
        probe=lambda _: next(probes),
    )

    assert code == 3
    assert report["status"] == "FAILED_POSTFLIGHT_GIT_DRIFT"


def test_production_requires_expected_git_sha(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    report, code = quality_gate.execute(
        repo,
        Path("quality"),
        None,
        probe=lambda _: _clean_probe(),
    )
    assert code == 3
    assert report["status"] == "FAILED_PREFLIGHT"
    assert "expected-git-sha" in report["error"]


def test_production_cannot_skip_phases(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    report, code = quality_gate.execute(
        repo,
        Path("quality"),
        "a" * 40,
        skip_sync=True,
        skip_full_suite=True,
        probe=lambda _: _clean_probe(),
    )
    assert code == 3
    assert report["status"] == "FAILED_PREFLIGHT"
    assert "only be skipped" in report["error"]


def test_parser_requires_expected_git_sha() -> None:
    parser = quality_gate.parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
