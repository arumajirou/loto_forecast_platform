from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.tirex2_campaign.lock_review import (
    APPLY_TOKEN,
    APPROVAL_FILENAME,
    EXPECTED_TIREX_ARTIFACT_HASHES,
    LOCK_FILENAME,
    REPORT_FILENAME,
    LockReviewError,
    build_approval,
    inspect_lock,
    install_reviewed_lock,
    sha256_file,
    validate_installed_review,
)

HASH = "sha256:" + "a" * 64
TIREX_HASH = sorted(EXPECTED_TIREX_ARTIFACT_HASHES)[0]


def _write_project(path: Path) -> None:
    path.write_text(
        """[project]
name = "loto-tirex2-supported"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "tirex-2==0.1.1",
  "torch==2.9.1",
  "numpy>=1.26,<3",
  "huggingface-hub==0.36.2",
  "pydantic>=2.10,<3",
]
""",
        encoding="utf-8",
    )


def _package(name: str, version: str, artifact_hash: str = HASH) -> str:
    return f'''[[package]]
name = "{name}"
version = "{version}"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files.pythonhosted.org/{name}.whl", hash = "{artifact_hash}" }}]
'''


def _write_lock(
    path: Path,
    *,
    tirex_hash: str = TIREX_HASH,
    tirex_source: str = '{ registry = "https://pypi.org/simple" }',
    numpy_version: str = "2.1.3",
    include_torch_hash: bool = True,
) -> None:
    torch_block = _package("torch", "2.9.1")
    if not include_torch_hash:
        torch_block = """[[package]]
name = "torch"
version = "2.9.1"
source = { registry = "https://pypi.org/simple" }
"""
    path.write_text(
        f'''version = 1
revision = 3
requires-python = ">=3.12,<3.13"

[[package]]
name = "loto-tirex2-supported"
version = "0.1.0"
source = {{ virtual = "." }}
dependencies = [
  {{ name = "tirex-2" }},
  {{ name = "torch" }},
  {{ name = "numpy" }},
  {{ name = "huggingface-hub" }},
  {{ name = "pydantic" }},
]

[[package]]
name = "tirex-2"
version = "0.1.1"
source = {tirex_source}
wheels = [{{ url = "https://files.pythonhosted.org/tirex.whl", hash = "{tirex_hash}" }}]

{torch_block}
{_package("numpy", numpy_version)}
{_package("huggingface-hub", "0.36.2")}
{_package("pydantic", "2.11.7")}
''',
        encoding="utf-8",
    )


def _candidate(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_project(candidate / "pyproject.toml")
    _write_lock(candidate / LOCK_FILENAME)
    report = inspect_lock(
        pyproject_path=candidate / "pyproject.toml",
        lock_path=candidate / LOCK_FILENAME,
        runtime_lane="tirex2-supported-py312",
    )
    (candidate / REPORT_FILENAME).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return candidate, report


def test_lock_review_accepts_bounded_direct_dependencies(tmp_path: Path) -> None:
    _write_project(tmp_path / "pyproject.toml")
    _write_lock(tmp_path / LOCK_FILENAME)
    report = inspect_lock(
        pyproject_path=tmp_path / "pyproject.toml",
        lock_path=tmp_path / LOCK_FILENAME,
        runtime_lane="tirex2-supported-py312",
    )
    assert report["status"] == "PASS"
    assert report["violations"] == []
    assert report["package_count"] == 6
    assert report["source_counts"] == {"registry": 5, "root-virtual": 1}


def test_lock_review_rejects_vcs_source(tmp_path: Path) -> None:
    _write_project(tmp_path / "pyproject.toml")
    _write_lock(tmp_path / LOCK_FILENAME, tirex_source='{ git = "https://example.invalid/x" }')
    report = inspect_lock(
        pyproject_path=tmp_path / "pyproject.toml",
        lock_path=tmp_path / LOCK_FILENAME,
        runtime_lane="tirex2-supported-py312",
    )
    assert report["status"] == "FAILED"
    assert any("forbidden source keys" in item for item in report["violations"])


def test_lock_review_rejects_missing_registry_hash(tmp_path: Path) -> None:
    _write_project(tmp_path / "pyproject.toml")
    _write_lock(tmp_path / LOCK_FILENAME, include_torch_hash=False)
    report = inspect_lock(
        pyproject_path=tmp_path / "pyproject.toml",
        lock_path=tmp_path / LOCK_FILENAME,
        runtime_lane="tirex2-supported-py312",
    )
    assert any("registry package lacks artifact hashes" in item for item in report["violations"])


def test_lock_review_rejects_incompatible_direct_version(tmp_path: Path) -> None:
    _write_project(tmp_path / "pyproject.toml")
    _write_lock(tmp_path / LOCK_FILENAME, numpy_version="3.0.0")
    report = inspect_lock(
        pyproject_path=tmp_path / "pyproject.toml",
        lock_path=tmp_path / LOCK_FILENAME,
        runtime_lane="tirex2-supported-py312",
    )
    assert any("direct dependency mismatch: numpy" in item for item in report["violations"])


def test_lock_review_rejects_unrecognized_tirex_artifact(tmp_path: Path) -> None:
    _write_project(tmp_path / "pyproject.toml")
    _write_lock(tmp_path / LOCK_FILENAME, tirex_hash=HASH)
    report = inspect_lock(
        pyproject_path=tmp_path / "pyproject.toml",
        lock_path=tmp_path / LOCK_FILENAME,
        runtime_lane="tirex2-supported-py312",
    )
    assert any("official wheel/sdist SHA-256" in item for item in report["violations"])


def test_approval_requires_passing_report_and_timezone(tmp_path: Path) -> None:
    _, report = _candidate(tmp_path)
    with pytest.raises(LockReviewError, match="timezone"):
        build_approval(report=report, reviewer="reviewer", reviewed_at="2026-08-06T08:00:00")
    approval = build_approval(
        report=report,
        reviewer="reviewer",
        reviewed_at="2026-08-06T08:00:00+09:00",
    )
    assert approval["decision"] == "APPROVED"
    assert approval["violation_count"] == 0


def test_dry_run_does_not_modify_environment(tmp_path: Path) -> None:
    candidate, _ = _candidate(tmp_path)
    environment = tmp_path / "environment"
    environment.mkdir()
    _write_project(environment / "pyproject.toml")
    result = install_reviewed_lock(
        candidate_path=candidate,
        environment_path=environment,
        runtime_lane="tirex2-supported-py312",
        reviewer="reviewer",
        reviewed_at="2026-08-06T08:00:00+09:00",
        expected_candidate_lock_sha256=sha256_file(candidate / LOCK_FILENAME),
        apply=False,
        approval_token=None,
    )
    assert result["status"] == "DRY_RUN"
    assert not (environment / LOCK_FILENAME).exists()


def test_apply_requires_token_and_installs_bound_artifacts(tmp_path: Path) -> None:
    candidate, _ = _candidate(tmp_path)
    environment = tmp_path / "environment"
    environment.mkdir()
    _write_project(environment / "pyproject.toml")
    lock_sha = sha256_file(candidate / LOCK_FILENAME)
    with pytest.raises(LockReviewError, match="approval token"):
        install_reviewed_lock(
            candidate_path=candidate,
            environment_path=environment,
            runtime_lane="tirex2-supported-py312",
            reviewer="reviewer",
            reviewed_at="2026-08-06T08:00:00+09:00",
            expected_candidate_lock_sha256=lock_sha,
            apply=True,
            approval_token="WRONG",
        )
    result = install_reviewed_lock(
        candidate_path=candidate,
        environment_path=environment,
        runtime_lane="tirex2-supported-py312",
        reviewer="reviewer",
        reviewed_at="2026-08-06T08:00:00+09:00",
        expected_candidate_lock_sha256=lock_sha,
        apply=True,
        approval_token=APPLY_TOKEN,
    )
    assert result["status"] == "PASS"
    assert (environment / LOCK_FILENAME).is_file()
    assert (environment / REPORT_FILENAME).is_file()
    assert (environment / APPROVAL_FILENAME).is_file()
    preflight = validate_installed_review(
        environment_path=environment,
        runtime_lane="tirex2-supported-py312",
    )
    assert preflight["status"] == "PASS"


def test_preflight_rejects_tampered_installed_lock(tmp_path: Path) -> None:
    candidate, _ = _candidate(tmp_path)
    environment = tmp_path / "environment"
    environment.mkdir()
    _write_project(environment / "pyproject.toml")
    install_reviewed_lock(
        candidate_path=candidate,
        environment_path=environment,
        runtime_lane="tirex2-supported-py312",
        reviewer="reviewer",
        reviewed_at="2026-08-06T08:00:00+09:00",
        expected_candidate_lock_sha256=sha256_file(candidate / LOCK_FILENAME),
        apply=True,
        approval_token=APPLY_TOKEN,
    )
    with (environment / LOCK_FILENAME).open("a", encoding="utf-8") as stream:
        stream.write("\n# tampered\n")
    with pytest.raises(LockReviewError, match="report does not match"):
        validate_installed_review(
            environment_path=environment,
            runtime_lane="tirex2-supported-py312",
        )
