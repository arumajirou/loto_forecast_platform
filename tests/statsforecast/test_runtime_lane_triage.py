from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.statsforecast.runtime_lane_triage import triage_end_to_end_run

COMMIT = "a" * 40


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _base_report(**overrides):
    report = {
        "formal_pass": False,
        "decision": "MERGE_BLOCKED",
        "expected_commit": COMMIT,
        "git_context": {"head": COMMIT, "working_tree_clean": True},
        "target_status": None,
        "target_archive": None,
        "admission_status": None,
        "seed": 1,
        "horizon": 1,
        "failures": [],
    }
    report.update(overrides)
    return report


def _run(tmp_path: Path, report: dict):
    source = tmp_path / "run"
    source.mkdir()
    _write_json(source / "END_TO_END_REPORT.json", report)
    return triage_end_to_end_run(source, tmp_path / "triage")


def test_classifies_clean_formal_pass_as_no_failure(tmp_path) -> None:
    result = _run(
        tmp_path,
        _base_report(
            formal_pass=True,
            decision="RUNTIME_CERTIFIED",
            target_status="PASS",
            admission_status="ADMITTED",
        ),
    )
    assert result.status == "NO_FAILURE"
    assert result.primary_classification == "NO_FAILURE"
    assert result.progress_percent == 100


def test_classifies_dirty_worktree_as_git_preflight(tmp_path) -> None:
    result = _run(
        tmp_path,
        _base_report(
            git_context={"head": COMMIT, "working_tree_clean": False},
            failures=["working tree is not clean"],
        ),
    )
    assert result.primary_classification == "GIT_PREFLIGHT"
    assert result.progress_percent == 10


def test_classifies_network_exception(tmp_path) -> None:
    source = tmp_path / "run"
    source.mkdir()
    _write_json(
        source / "END_TO_END_REPORT.json",
        _base_report(failures=["RuntimeError: network unavailable"]),
    )
    _write_json(
        source / "END_TO_END_EXCEPTION.json",
        {"type": "RuntimeError", "message": "DNS resolution failed for pypi.org"},
    )
    result = triage_end_to_end_run(source, tmp_path / "triage")
    assert result.primary_classification == "DEPENDENCY_OR_NETWORK"


def test_classifies_admission_rejection(tmp_path) -> None:
    source = tmp_path / "run"
    source.mkdir()
    _write_json(
        source / "END_TO_END_REPORT.json",
        _base_report(
            target_status="PASS",
            target_archive="result.zip",
            admission_status="REJECTED",
            failures=["admission rejected package"],
        ),
    )
    _write_json(
        source / "admission" / "ADMISSION_REPORT.json",
        {"formal_pass": False, "failures": ["checksum mismatch"]},
    )
    result = triage_end_to_end_run(source, tmp_path / "triage")
    payload = json.loads(result.classification_path.read_text(encoding="utf-8"))
    codes = {item["code"] for item in payload["classifications"]}
    assert "ADMISSION_REJECTED" in codes
    assert "EVIDENCE_INTEGRITY" in codes


def test_classifies_failed_model_matrix(tmp_path) -> None:
    source = tmp_path / "run"
    source.mkdir()
    _write_json(
        source / "END_TO_END_REPORT.json",
        _base_report(target_status="FAILED", target_archive="result.zip"),
    )
    _write_json(
        source / "runtime" / "RUNTIME_LANE_REPORT.json",
        {"certification_returncode": 2},
    )
    _write_json(
        source / "runtime" / "VERIFICATION_REPORT.json",
        {"formal_pass": False},
    )
    _write_json(
        source / "runtime" / "MODEL_RUNTIME_MATRIX.json",
        [{"model_name": "AutoARIMA", "status": "EXECUTION_FAILED"}],
    )
    result = triage_end_to_end_run(source, tmp_path / "triage")
    payload = json.loads(result.classification_path.read_text(encoding="utf-8"))
    assert any(item["code"] == "MODEL_RUNTIME" for item in payload["classifications"])


def test_evidence_failure_has_verification_remediation(tmp_path) -> None:
    result = _run(
        tmp_path,
        _base_report(failures=["archive SHA-256 digest mismatch"]),
    )
    plan = json.loads(result.remediation_path.read_text(encoding="utf-8"))
    assert any(step["step_id"] == "VERIFY_EVIDENCE" for step in plan["steps"])


def test_missing_end_to_end_report_is_rejected(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        triage_end_to_end_run(tmp_path / "missing", tmp_path / "triage")


def test_writes_markdown_and_checksums(tmp_path) -> None:
    result = _run(tmp_path, _base_report(failures=["unknown failure"])).output_dir
    assert (result / "FAILURE_CLASSIFICATION.json").is_file()
    assert (result / "REMEDIATION_PLAN.json").is_file()
    assert (result / "REMEDIATION_PLAN.md").is_file()
    rows = (result / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 3
