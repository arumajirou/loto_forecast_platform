from __future__ import annotations

from pathlib import Path

import pytest

from loto.merlion_campaign.bootstrap_resume import _canonical_sha256, build_resume_plan


def _preflight(
    *,
    python_found: bool,
    github: bool = True,
    index: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "merlion-bootstrap-preflight-v1",
        "created_at_utc": "2026-08-05T00:00:00+00:00",
        "status": "READY" if python_found else "READY_WITH_PYTHON_DOWNLOAD",
        "can_attempt_bootstrap": True,
        "root": "/repo",
        "environment_directory": "/repo/environments/merlion-core-py311",
        "uv": {"found": True, "path": "/usr/bin/uv", "version": "uv 0.10.0"},
        "python_311": {
            "found": python_found,
            "path": "/opt/python3.11" if python_found else None,
            "version": "Python 3.11.14" if python_found else None,
        },
        "filesystem": {},
        "disk": {"sufficient": True},
        "network_dns": [
            {"host": "pypi.org", "reachable": index},
            {"host": "files.pythonhosted.org", "reachable": index},
            {"host": "github.com", "reachable": github},
        ],
        "blockers": [],
        "warnings": [],
    }
    payload["report_sha256"] = _canonical_sha256(payload)
    return payload


def test_resume_plan_uses_existing_python(tmp_path: Path) -> None:
    plan = build_resume_plan(_preflight(python_found=True), tmp_path, run_id="run-1")
    assert plan["status"] == "READY_TO_BOOTSTRAP"
    assert plan["strategy"] == "USE_EXISTING_PYTHON_311"
    assert plan["python_path"] == "/opt/python3.11"
    assert plan["steps"] == [
        {"name": "bootstrap", "command": ["bash", "scripts/bootstrap_merlion_core_env.sh"]}
    ]
    assert plan["safety"]["sudo_allowed"] is False


def test_resume_plan_uses_repo_scoped_managed_python(tmp_path: Path) -> None:
    managed = tmp_path / "managed-python"
    plan = build_resume_plan(
        _preflight(python_found=False),
        tmp_path,
        run_id="run-2",
        managed_python_dir=managed,
    )
    assert plan["status"] == "READY_TO_PROVISION_PYTHON"
    assert plan["strategy"] == "INSTALL_UV_MANAGED_PYTHON_311"
    install = plan["steps"][0]["command"]
    assert install[:4] == ["uv", "python", "install", "3.11"]
    assert "--no-bin" in install
    assert plan["environment"]["UV_PYTHON_INSTALL_DIR"] == str(managed.resolve())


def test_resume_plan_blocks_when_network_sources_are_unavailable(tmp_path: Path) -> None:
    plan = build_resume_plan(
        _preflight(python_found=False, github=False, index=False),
        tmp_path,
        run_id="run-3",
    )
    assert plan["status"] == "BLOCKED"
    assert "PYTHON_311_UNAVAILABLE_AND_DOWNLOAD_BLOCKED" in plan["blockers"]
    assert "PACKAGE_INDEX_DNS_UNAVAILABLE" in plan["blockers"]


def test_resume_plan_rejects_tampered_preflight(tmp_path: Path) -> None:
    preflight = _preflight(python_found=True)
    preflight["status"] = "BLOCKED"
    with pytest.raises(ValueError, match="report_sha256 mismatch"):
        build_resume_plan(preflight, tmp_path, run_id="run-4")
