from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.moirai2_campaign.lock_review import (
    APPROVAL_FILENAME,
    REPORT_FILENAME,
    LockReviewError,
    build_approval,
    inspect_lock,
    sha256_file,
    sha256_payload,
    validate_installed_review,
)


PYPROJECT = """
[project]
name = "test-lane"
version = "0.1.0"
requires-python = ">=3.11,<3.12"
dependencies = [
  "uni2ts==2.0.0",
  "gluonts==0.14.4",
  "huggingface-hub==0.36.2",
  "numpy==1.26.4",
  "pandas==2.2.3",
  "torch==2.4.1",
]
""".strip()

HASH_A = "sha256:" + ("a" * 64)
HASH_B = "sha256:" + ("b" * 64)

LOCK = f"""
version = 1
revision = 3

[[package]]
name = "test-lane"
version = "0.1.0"
source = {{ virtual = "." }}
dependencies = [
  {{ name = "uni2ts" }},
  {{ name = "gluonts" }},
  {{ name = "huggingface-hub" }},
  {{ name = "numpy" }},
  {{ name = "pandas" }},
  {{ name = "torch" }},
]

[[package]]
name = "uni2ts"
version = "2.0.0"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/uni2ts.tar.gz", hash = "{HASH_A}", size = 1 }}

[[package]]
name = "gluonts"
version = "0.14.4"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files/gluonts.whl", hash = "{HASH_B}", size = 1 }}]

[[package]]
name = "huggingface-hub"
version = "0.36.2"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/hf.tar.gz", hash = "{HASH_A}", size = 1 }}

[[package]]
name = "numpy"
version = "1.26.4"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files/numpy.whl", hash = "{HASH_B}", size = 1 }}]

[[package]]
name = "pandas"
version = "2.2.3"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/pandas.tar.gz", hash = "{HASH_A}", size = 1 }}
dependencies = [{{ name = "numpy" }}]

[[package]]
name = "torch"
version = "2.4.1"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://files/torch.whl", hash = "{HASH_B}", size = 1 }}]
""".strip()


def _candidate(tmp_path: Path, lock: str = LOCK) -> tuple[Path, Path]:
    pyproject = tmp_path / "pyproject.toml"
    lock_path = tmp_path / "uv.lock"
    pyproject.write_text(PYPROJECT + "\n", encoding="utf-8")
    lock_path.write_text(lock + "\n", encoding="utf-8")
    return pyproject, lock_path


def _installed(tmp_path: Path) -> Path:
    environment = tmp_path / "environment"
    environment.mkdir()
    pyproject, lock_path = _candidate(tmp_path)
    (environment / "pyproject.toml").write_bytes(pyproject.read_bytes())
    (environment / "uv.lock").write_bytes(lock_path.read_bytes())
    report = inspect_lock(
        pyproject_path=environment / "pyproject.toml",
        lock_path=environment / "uv.lock",
        runtime_lane="supported-py311",
    )
    approval = build_approval(
        report=report,
        reviewer="reviewer@example.invalid",
        reviewed_at="2026-08-06T00:00:00+09:00",
    )
    (environment / REPORT_FILENAME).write_text(
        json.dumps(report, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (environment / APPROVAL_FILENAME).write_text(
        json.dumps(approval, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return environment


def test_registry_lock_review_passes_and_retains_inventory(tmp_path: Path) -> None:
    pyproject, lock_path = _candidate(tmp_path)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    assert report["status"] == "PASS"
    assert report["package_count"] == 7
    assert report["dependency_edge_count"] == 7
    assert report["direct_dependencies"]["uni2ts"] == "2.0.0"
    assert report["source_counts"] == {"registry": 6, "root-virtual": 1}
    assert len(report["inventory_sha256"]) == 64


@pytest.mark.parametrize(
    ("source_fragment", "match"),
    [
        ('source = { git = "https://example.invalid/repo.git" }', "forbidden source"),
        ('source = { path = "../local-package" }', "forbidden source"),
        ('source = { editable = "../local-package" }', "forbidden source"),
    ],
)
def test_non_registry_dependency_sources_fail(
    tmp_path: Path,
    source_fragment: str,
    match: str,
) -> None:
    changed = LOCK.replace(
        'source = { registry = "https://pypi.org/simple" }',
        source_fragment,
        1,
    )
    pyproject, lock_path = _candidate(tmp_path, changed)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    assert report["status"] == "FAILED"
    assert any(match in violation for violation in report["violations"])


def test_registry_package_without_hash_fails(tmp_path: Path) -> None:
    changed = LOCK.replace(
        f'sdist = {{ url = "https://files/uni2ts.tar.gz", hash = "{HASH_A}", size = 1 }}',
        "",
    )
    pyproject, lock_path = _candidate(tmp_path, changed)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    assert any("lacks artifact hashes" in item for item in report["violations"])


def test_invalid_artifact_hash_fails(tmp_path: Path) -> None:
    changed = LOCK.replace(HASH_A, "sha256:not-a-valid-digest", 1)
    pyproject, lock_path = _candidate(tmp_path, changed)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    assert any("invalid artifact hashes" in item for item in report["violations"])


def test_direct_version_mismatch_fails(tmp_path: Path) -> None:
    changed = LOCK.replace(
        'name = "uni2ts"\nversion = "2.0.0"',
        'name = "uni2ts"\nversion = "1.9.0"',
    )
    pyproject, lock_path = _candidate(tmp_path, changed)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    assert any("direct dependency mismatch" in item for item in report["violations"])


def test_unresolved_dependency_edge_fails(tmp_path: Path) -> None:
    changed = LOCK.replace(
        'dependencies = [{ name = "numpy" }]',
        'dependencies = [{ name = "numpy" }, { name = "missing-package" }]',
    )
    pyproject, lock_path = _candidate(tmp_path, changed)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    assert any("unresolved dependency names" in item for item in report["violations"])


def test_multiple_versions_are_retained_as_warning(tmp_path: Path) -> None:
    duplicate = f"""
[[package]]
name = "numpy"
version = "2.0.0"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files/numpy2.tar.gz", hash = "{HASH_A}", size = 1 }}
"""
    pyproject, lock_path = _candidate(tmp_path, LOCK + "\n" + duplicate)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    assert report["status"] == "PASS"
    assert report["warnings"]
    assert report["locked_versions"]["numpy"] == ["1.26.4", "2.0.0"]


def test_failed_report_cannot_be_approved(tmp_path: Path) -> None:
    changed = LOCK.replace(
        'source = { registry = "https://pypi.org/simple" }',
        'source = { git = "https://example.invalid/repo.git" }',
        1,
    )
    pyproject, lock_path = _candidate(tmp_path, changed)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    with pytest.raises(LockReviewError, match="cannot be approved"):
        build_approval(
            report=report,
            reviewer="reviewer",
            reviewed_at="2026-08-06T00:00:00+09:00",
        )


def test_approval_requires_timezone(tmp_path: Path) -> None:
    pyproject, lock_path = _candidate(tmp_path)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    with pytest.raises(LockReviewError, match="timezone"):
        build_approval(
            report=report,
            reviewer="reviewer",
            reviewed_at="2026-08-06T00:00:00",
        )


def test_installed_review_validates_cross_hashes(tmp_path: Path) -> None:
    environment = _installed(tmp_path)
    evidence = validate_installed_review(
        environment_path=environment,
        runtime_lane="supported-py311",
    )
    assert evidence["reviewer"] == "reviewer@example.invalid"
    assert evidence["lock_sha256"] == sha256_file(environment / "uv.lock")
    assert evidence["package_count"] == 7


def test_installed_review_rejects_tampered_lock(tmp_path: Path) -> None:
    environment = _installed(tmp_path)
    with (environment / "uv.lock").open("a", encoding="utf-8") as stream:
        stream.write("# tampered\n")
    with pytest.raises(LockReviewError, match="lock_sha256"):
        validate_installed_review(
            environment_path=environment,
            runtime_lane="supported-py311",
        )


def test_installed_review_rejects_tampered_report(tmp_path: Path) -> None:
    environment = _installed(tmp_path)
    report_path = environment / REPORT_FILENAME
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["warnings"] = ["tampered"]
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(LockReviewError, match="report_sha256"):
        validate_installed_review(
            environment_path=environment,
            runtime_lane="supported-py311",
        )


def test_installed_review_rejects_missing_approval(tmp_path: Path) -> None:
    environment = _installed(tmp_path)
    (environment / APPROVAL_FILENAME).unlink()
    with pytest.raises(LockReviewError, match="artifacts are missing"):
        validate_installed_review(
            environment_path=environment,
            runtime_lane="supported-py311",
        )


def test_installed_review_rejects_lane_mismatch(tmp_path: Path) -> None:
    environment = _installed(tmp_path)
    with pytest.raises(LockReviewError, match="runtime lane"):
        validate_installed_review(
            environment_path=environment,
            runtime_lane="cuda13-experimental",
        )


def test_approval_hashes_report_payload(tmp_path: Path) -> None:
    pyproject, lock_path = _candidate(tmp_path)
    report = inspect_lock(
        pyproject_path=pyproject,
        lock_path=lock_path,
        runtime_lane="supported-py311",
    )
    approval = build_approval(
        report=report,
        reviewer="reviewer",
        reviewed_at="2026-08-06T00:00:00+09:00",
    )
    assert approval["report_sha256"] == sha256_payload(report)
    assert approval["lock_sha256"] == sha256_file(lock_path)
