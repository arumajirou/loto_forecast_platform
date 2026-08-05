from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from loto.merlion_campaign.bootstrap_evidence import package_bootstrap_evidence
from loto.merlion_campaign.bootstrap_evidence_verify import verify_bootstrap_evidence_zip
from loto.merlion_campaign.bootstrap_resume import _canonical_sha256, build_resume_plan


def _preflight(*, python_found: bool, github: bool = True, index: bool = True) -> dict[str, object]:
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


def _write_blocked_run(run_dir: Path, *, run_id: str) -> None:
    run_dir.mkdir(parents=True)
    preflight = _preflight(python_found=False, github=False, index=False)
    plan = build_resume_plan(preflight, run_dir.parent, run_id=run_id)
    (run_dir / "PREFLIGHT.json").write_text(
        json.dumps(preflight, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "BOOTSTRAP_PLAN.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "BOOTSTRAP_FAILURE.json").write_text(
        json.dumps(
            {
                "schema_version": "merlion-bootstrap-failure-v1",
                "status": "BLOCKED",
                "run_id": run_id,
                "stage": "resume_plan",
                "exit_code": 2,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "exit_code").write_text("2\n", encoding="utf-8")


def test_blocked_evidence_is_packaged_and_verified(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    (env_dir / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    _write_blocked_run(run_dir, run_id="blocked-1")
    archive = tmp_path / "blocked.zip"
    result = package_bootstrap_evidence(run_dir, env_dir, archive, run_id="blocked-1")
    verification = verify_bootstrap_evidence_zip(archive)
    assert result["status"] == "BOOTSTRAP_BLOCKED"
    assert verification["status"] == "PASS"
    assert verification["evidence_status"] == "BOOTSTRAP_BLOCKED"
    assert archive.with_suffix(".zip.sha256").is_file()


def test_pass_evidence_requires_audited_lock_and_is_reproducible(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    env_dir = tmp_path / "env"
    run_dir.mkdir()
    env_dir.mkdir()
    preflight = _preflight(python_found=True)
    (run_dir / "PREFLIGHT.json").write_text(
        json.dumps(preflight, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "DEPENDENCY_AUDIT.json").write_text(
        json.dumps({"status": "PASS"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "DEPENDENCY_INVENTORY.csv").write_text("name,version\n", encoding="utf-8")
    (run_dir / "exit_code").write_text("0\n", encoding="utf-8")
    (env_dir / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (env_dir / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    package_bootstrap_evidence(run_dir, env_dir, first, run_id="pass-1")
    package_bootstrap_evidence(run_dir, env_dir, second, run_id="pass-1")
    assert first.read_bytes() == second.read_bytes()
    assert verify_bootstrap_evidence_zip(first)["evidence_status"] == "BOOTSTRAP_PASS"


def test_evidence_packager_refuses_overwrite(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    (env_dir / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    _write_blocked_run(run_dir, run_id="blocked-immutable")
    archive = tmp_path / "immutable.zip"
    package_bootstrap_evidence(
        run_dir,
        env_dir,
        archive,
        run_id="blocked-immutable",
    )
    with pytest.raises(ValueError, match="output already exists"):
        package_bootstrap_evidence(
            run_dir,
            env_dir,
            archive,
            run_id="blocked-immutable",
        )


def test_evidence_verifier_rejects_tampering(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    (env_dir / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    _write_blocked_run(run_dir, run_id="blocked-2")
    archive = tmp_path / "original.zip"
    tampered = tmp_path / "tampered.zip"
    package_bootstrap_evidence(run_dir, env_dir, archive, run_id="blocked-2")
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "run/PREFLIGHT.json":
                data = b'{"tampered": true}\n'
            target.writestr(info, data)
    with pytest.raises(ValueError, match="manifest size mismatch|manifest SHA-256 mismatch"):
        verify_bootstrap_evidence_zip(tampered)
