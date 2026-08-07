from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.basicts_campaign.lock_audit import (
    EXPECTED_UPSTREAM_REVISION,
    LockAuditError,
    verify_environment_pyproject,
    verify_workspace_metadata,
)


def _write_pyproject(path: Path, *, numpy: str = "numpy==1.24.4") -> None:
    path.write_text(
        "\n".join(
            [
                "[project]",
                'name = "loto-basicts-provider"',
                'version = "0.1.0"',
                'requires-python = ">=3.11,<3.12"',
                "dependencies = [",
                (
                    '  "BasicTS @ git+https://github.com/GestaltCogTeam/BasicTS.git@'
                    f'{EXPECTED_UPSTREAM_REVISION}",'
                ),
                '  "torch==2.9.1",',
                f'  "{numpy}",',
                '  "pydantic>=2.10,<3",',
                "]",
                "",
                "[tool.uv]",
                "package = false",
                'required-version = "==0.12.0"',
                'exclude-newer = "2026-08-05T00:00:00Z"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _metadata() -> dict[str, object]:
    packages = {
        "basicts": (
            "1.1.0",
            {
                "git": {
                    "url": "https://github.com/GestaltCogTeam/BasicTS",
                    "commit": EXPECTED_UPSTREAM_REVISION,
                }
            },
        ),
        "easy-torch": ("1.3.3", {"registry": {"url": "https://pypi.org/simple"}}),
        "numpy": ("1.24.4", {"registry": {"url": "https://pypi.org/simple"}}),
        "setuptools": ("59.5.0", {"registry": {"url": "https://pypi.org/simple"}}),
        "torch": ("2.9.1", {"registry": {"url": "https://pypi.org/simple"}}),
        "transformers": ("4.40.1", {"registry": {"url": "https://pypi.org/simple"}}),
    }
    resolution = {
        f"{name}=={version}": {
            "kind": "package",
            "name": name,
            "version": version,
            "source": source,
            "dependencies": [],
        }
        for name, (version, source) in packages.items()
    }
    return {
        "schema": {"version": "preview"},
        "requires_python": ">=3.11,<3.12",
        "environment": {
            "python": {"version": "3.11.13", "implementation": "cpython"}
        },
        "conflicts": {"sets": []},
        "resolution": resolution,
    }


def test_verify_environment_pyproject_accepts_frozen_contract(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    _write_pyproject(path)

    evidence = verify_environment_pyproject(path)

    assert evidence["uv_version"] == "0.12.0"
    assert "numpy==1.24.4" in evidence["direct_dependencies"]


def test_verify_environment_pyproject_rejects_numpy_2(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    _write_pyproject(path, numpy="numpy>=2.0,<3")

    with pytest.raises(LockAuditError, match="direct dependencies differ"):
        verify_environment_pyproject(path)


def test_verify_workspace_metadata_accepts_exact_resolution(tmp_path: Path) -> None:
    path = tmp_path / "UV_WORKSPACE_METADATA.json"
    path.write_text(json.dumps(_metadata()), encoding="utf-8")

    evidence = verify_workspace_metadata(path)

    assert evidence["python_version"] == "3.11.13"
    assert evidence["packages"]["basicts"]["revision"] == EXPECTED_UPSTREAM_REVISION


def test_verify_workspace_metadata_rejects_wrong_revision(tmp_path: Path) -> None:
    payload = _metadata()
    basicts = payload["resolution"]["basicts==1.1.0"]
    basicts["source"]["git"]["commit"] = "0" * 40
    path = tmp_path / "UV_WORKSPACE_METADATA.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LockAuditError, match="frozen commit"):
        verify_workspace_metadata(path)


def test_verify_workspace_metadata_rejects_transformers_drift(tmp_path: Path) -> None:
    payload = _metadata()
    payload["resolution"]["transformers==4.40.1"]["version"] = "4.57.6"
    path = tmp_path / "UV_WORKSPACE_METADATA.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LockAuditError, match="resolved version mismatch for transformers"):
        verify_workspace_metadata(path)


def test_verify_workspace_metadata_rejects_wrong_python_lane(tmp_path: Path) -> None:
    payload = _metadata()
    payload["environment"]["python"]["version"] = "3.12.8"
    path = tmp_path / "UV_WORKSPACE_METADATA.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LockAuditError, match="not running Python 3.11"):
        verify_workspace_metadata(path)


def test_main_writes_audited_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from loto.basicts_campaign import lock_audit

    pyproject = tmp_path / "pyproject.toml"
    metadata = tmp_path / "metadata.json"
    output = tmp_path / "report.json"
    _write_pyproject(pyproject)
    metadata.write_text(json.dumps(_metadata()), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "lock-audit",
            "--pyproject",
            str(pyproject),
            "--metadata",
            str(metadata),
            "--output",
            str(output),
        ],
    )

    assert lock_audit.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "PASS"
    assert output.with_suffix(".json.sha256").is_file()
