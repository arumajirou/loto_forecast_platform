from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from loto.merlion_campaign.dependency_gate import (
    audit_uv_lock,
    build_preflight_report,
    write_inventory_csv,
)


def _disk_usage(_path: object) -> SimpleNamespace:
    return SimpleNamespace(total=20 * 1024**3, used=1, free=19 * 1024**3)


def _resolver_ok(host: str, port: int, type: int) -> list[tuple[object, ...]]:
    del port, type
    return [(None, None, None, None, (f"192.0.2.{len(host)}", 443))]


def _resolver_fail(host: str, port: int, type: int) -> list[tuple[object, ...]]:
    del host, port, type
    raise OSError("dns blocked")


def _runner_factory(*, python_found: bool) -> object:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        if command[-1] == "--version" and command[0].endswith("uv"):
            return subprocess.CompletedProcess(command, 0, b"uv 0.10.0\n", b"")
        if "python" in command and "find" in command:
            if python_found:
                return subprocess.CompletedProcess(command, 0, b"/opt/python3.11\n", b"")
            return subprocess.CompletedProcess(command, 2, b"", b"not found")
        if command[0] == "/opt/python3.11":
            return subprocess.CompletedProcess(command, 0, b"Python 3.11.14\n", b"")
        raise AssertionError(command)

    return runner


def _project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    env_dir = root / "environments/merlion-core-py311"
    env_dir.mkdir(parents=True)
    pyproject = env_dir / "pyproject.toml"
    pyproject.write_text(
        """[project]
name = "loto-merlion-provider"
requires-python = ">=3.11,<3.12"
""",
        encoding="utf-8",
    )
    return root, env_dir


def test_preflight_blocks_without_uv(tmp_path: Path) -> None:
    root, env_dir = _project(tmp_path)
    report = build_preflight_report(
        root,
        env_dir,
        which=lambda _name: None,
        resolver=_resolver_ok,
        disk_usage=_disk_usage,
    )
    assert report["status"] == "BLOCKED"
    assert report["can_attempt_bootstrap"] is False
    assert "UV_NOT_FOUND" in report["blockers"]


def test_preflight_blocks_when_python_and_dns_are_unavailable(tmp_path: Path) -> None:
    root, env_dir = _project(tmp_path)
    report = build_preflight_report(
        root,
        env_dir,
        which=lambda _name: "/opt/uv",
        runner=_runner_factory(python_found=False),
        resolver=_resolver_fail,
        disk_usage=_disk_usage,
    )
    assert report["status"] == "BLOCKED"
    assert "PYTHON_311_UNAVAILABLE_AND_DOWNLOAD_BLOCKED" in report["blockers"]
    assert "PACKAGE_INDEX_DNS_UNAVAILABLE" in report["warnings"]


def test_preflight_allows_managed_python_download(tmp_path: Path) -> None:
    root, env_dir = _project(tmp_path)
    report = build_preflight_report(
        root,
        env_dir,
        which=lambda _name: "/opt/uv",
        runner=_runner_factory(python_found=False),
        resolver=_resolver_ok,
        disk_usage=_disk_usage,
    )
    assert report["status"] == "READY_WITH_PYTHON_DOWNLOAD"
    assert report["can_attempt_bootstrap"] is True
    assert len(report["report_sha256"]) == 64


def _registry_package(name: str, version: str) -> str:
    wheel = f"https://files.pythonhosted.org/packages/{name}-{version}.whl"
    return f"""
[[package]]
name = "{name}"
version = "{version}"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [
  {{ url = "{wheel}", hash = "sha256:{"a" * 64}", size = 1 }},
]
"""


def _write_lock(tmp_path: Path, package_blocks: str) -> tuple[Path, Path]:
    pyproject = tmp_path / "pyproject.toml"
    lock = tmp_path / "uv.lock"
    pyproject.write_text(
        """[project]
name = "loto-merlion-provider"
requires-python = ">=3.11,<3.12"
""",
        encoding="utf-8",
    )
    lock.write_text(
        """version = 1
revision = 3
requires-python = ">=3.11,<3.12"

[[package]]
name = "loto-merlion-provider"
version = "0.1.0"
source = { virtual = "." }
"""
        + package_blocks,
        encoding="utf-8",
    )
    return lock, pyproject


def test_lock_audit_accepts_pinned_registry_sources(tmp_path: Path) -> None:
    lock, pyproject = _write_lock(
        tmp_path,
        _registry_package("salesforce-merlion", "2.0.4") + _registry_package("numpy", "1.26.4"),
    )
    report = audit_uv_lock(lock, pyproject)
    assert report["status"] == "PASS"
    assert report["package_count"] == 3
    assert report["artifact_count"] == 2
    assert report["sha256_artifact_count"] == 2


def test_lock_audit_rejects_untrusted_git_source(tmp_path: Path) -> None:
    git_package = """
[[package]]
name = "unsafe-package"
version = "1.0.0"
source = { git = "https://example.invalid/repo.git" }
"""
    lock, pyproject = _write_lock(
        tmp_path,
        _registry_package("salesforce-merlion", "2.0.4")
        + _registry_package("numpy", "1.26.4")
        + git_package,
    )
    report = audit_uv_lock(lock, pyproject)
    assert report["status"] == "BLOCKED"
    assert any(value.startswith("UNTRUSTED_SOURCE:unsafe-package") for value in report["blockers"])


def test_lock_audit_rejects_wrong_merlion_and_numpy_major(tmp_path: Path) -> None:
    lock, pyproject = _write_lock(
        tmp_path,
        _registry_package("salesforce-merlion", "2.0.3") + _registry_package("numpy", "2.0.0"),
    )
    report = audit_uv_lock(lock, pyproject)
    assert report["status"] == "BLOCKED"
    assert "MERLION_VERSION_MISMATCH:2.0.3" in report["blockers"]
    assert "NUMPY_MAJOR_NOT_ISOLATED:2.0.0" in report["blockers"]


def test_inventory_csv_is_sorted_and_complete(tmp_path: Path) -> None:
    lock, pyproject = _write_lock(
        tmp_path,
        _registry_package("salesforce-merlion", "2.0.4") + _registry_package("numpy", "1.26.4"),
    )
    report = audit_uv_lock(lock, pyproject)
    output = tmp_path / "inventory.csv"
    write_inventory_csv(output, report["inventory"])
    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("name,version,source_kind")
    assert lines[1].startswith("loto-merlion-provider,0.1.0,virtual")
    assert lines[2].startswith("numpy,1.26.4,registry")
    assert lines[3].startswith("salesforce-merlion,2.0.4,registry")
    json.dumps(report)
