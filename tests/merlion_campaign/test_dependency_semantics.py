from __future__ import annotations

from pathlib import Path

import pytest

from loto.merlion_campaign import dependency_semantics
from loto.merlion_campaign.dependency_gate import _canonical_sha256
from loto.merlion_campaign.dependency_semantics import (
    PythonConstraintError,
    audit_uv_lock_semantic,
    python_constraints_equivalent,
)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("==3.11.*", ">=3.11,<3.12"),
        (">=3.11.0,<3.12.0", "==3.11.*"),
        (" >=3.11 , <3.12 ", "==3.11.*"),
    ],
)
def test_python_constraints_equivalent_for_python_311(
    left: str,
    right: str,
) -> None:
    assert python_constraints_equivalent(left, right) is True


@pytest.mark.parametrize(
    "broader",
    [
        ">=3.10,<3.12",
        ">=3.11,<3.13",
        ">=3.11",
    ],
)
def test_python_constraints_reject_broader_ranges(broader: str) -> None:
    assert python_constraints_equivalent(">=3.11,<3.12", broader) is False


def test_python_constraints_reject_unsupported_clause() -> None:
    with pytest.raises(PythonConstraintError):
        python_constraints_equivalent("==3.11.*", "^3.11")


def _base_report(lock_constraint: str) -> dict[str, object]:
    report: dict[str, object] = {
        "schema_version": "merlion-uv-lock-audit-v1",
        "status": "BLOCKED",
        "requires_python": lock_constraint,
        "blockers": [f"REQUIRES_PYTHON_MISMATCH:{lock_constraint}:>=3.11,<3.12"],
        "warnings": [],
        "inventory": [],
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def _pyproject(tmp_path: Path, constraint: str = ">=3.11,<3.12") -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        f'[project]\nname = "test"\nrequires-python = "{constraint}"\n',
        encoding="utf-8",
    )
    return path


def test_semantic_audit_removes_false_positive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependency_semantics,
        "audit_uv_lock",
        lambda _lock, _project: _base_report("==3.11.*"),
    )
    lock = tmp_path / "uv.lock"
    lock.write_text('requires-python = "==3.11.*"\n', encoding="utf-8")
    report = audit_uv_lock_semantic(lock, _pyproject(tmp_path))
    assert report["status"] == "PASS"
    assert report["blockers"] == []
    assert report["requires_python_equivalent"] is True
    recorded = report["report_sha256"]
    without_hash = {key: value for key, value in report.items() if key != "report_sha256"}
    assert recorded == _canonical_sha256(without_hash)


def test_semantic_audit_keeps_real_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependency_semantics,
        "audit_uv_lock",
        lambda _lock, _project: _base_report(">=3.10,<3.12"),
    )
    lock = tmp_path / "uv.lock"
    lock.write_text('requires-python = ">=3.10,<3.12"\n', encoding="utf-8")
    report = audit_uv_lock_semantic(lock, _pyproject(tmp_path))
    assert report["status"] == "BLOCKED"
    assert report["requires_python_equivalent"] is False
    assert report["blockers"] == ["REQUIRES_PYTHON_MISMATCH:>=3.10,<3.12:>=3.11,<3.12"]
