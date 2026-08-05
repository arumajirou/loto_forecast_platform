from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from loto.statsforecast.runtime_lane_remediation import (
    execute_bounded_remediation,
    verify_triage_evidence,
)

_COMMIT = "a" * 40


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_sums(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            rows.append(f"{_sha256(path)}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _e2e(tmp_path: Path) -> Path:
    root = tmp_path / "source-e2e"
    root.mkdir()
    _write_json(
        root / "END_TO_END_REPORT.json",
        {"formal_pass": False, "decision": "MERGE_BLOCKED"},
    )
    return root


def _triage(tmp_path: Path, classification: str) -> tuple[Path, Path]:
    source = _e2e(tmp_path)
    triage = tmp_path / "triage"
    triage.mkdir()
    _write_json(
        triage / "FAILURE_CLASSIFICATION.json",
        {
            "primary_classification": classification,
            "source_end_to_end_dir": str(source),
            "source_report_sha256": _sha256(source / "END_TO_END_REPORT.json"),
        },
    )
    _write_json(
        triage / "REMEDIATION_PLAN.json",
        {
            "status": "REMEDIATION_REQUIRED",
            "steps": [{"commands": ["touch SHOULD_NOT_EXIST"]}],
        },
    )
    _write_sums(triage)
    return triage, source


@dataclass
class _Result:
    run_id: str
    output_dir: Path
    report_path: Path
    decision: str
    formal_pass: bool


def _runner_factory(tmp_path: Path, outcomes: list[object], calls: list[dict]):
    def runner(repo_root: Path, output_root: Path, **kwargs):
        calls.append(kwargs)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        run_dir = output_root / kwargs["run_id"]
        run_dir.mkdir(parents=True)
        report = run_dir / "END_TO_END_REPORT.json"
        _write_json(report, {"formal_pass": bool(outcome)})
        return _Result(
            run_id=kwargs["run_id"],
            output_dir=run_dir,
            report_path=report,
            decision="RUNTIME_CERTIFIED" if outcome else "MERGE_BLOCKED",
            formal_pass=bool(outcome),
        )

    return runner


def _clean_git(_repo: Path) -> dict:
    return {"head": _COMMIT, "working_tree_clean": True}


def test_no_failure_requires_no_rerun(tmp_path: Path) -> None:
    triage, source = _triage(tmp_path, "NO_FAILURE")
    calls = []
    result = execute_bounded_remediation(
        tmp_path,
        triage,
        tmp_path / "out",
        source_end_to_end_dir=source,
        expected_commit=_COMMIT,
        end_to_end_runner=_runner_factory(tmp_path, [True], calls),
        git_context_fn=_clean_git,
    )
    assert result.formal_pass is True
    assert result.status == "NOT_REQUIRED"
    assert calls == []


def test_git_preflight_requires_manual_action(tmp_path: Path) -> None:
    triage, source = _triage(tmp_path, "GIT_PREFLIGHT")
    result = execute_bounded_remediation(
        tmp_path,
        triage,
        tmp_path / "out",
        source_end_to_end_dir=source,
        expected_commit=_COMMIT,
        git_context_fn=_clean_git,
    )
    assert result.formal_pass is False
    assert result.status == "MANUAL_ACTION_REQUIRED"


def test_retryable_classification_can_certify(tmp_path: Path) -> None:
    triage, source = _triage(tmp_path, "DEPENDENCY_OR_NETWORK")
    calls = []
    result = execute_bounded_remediation(
        tmp_path,
        triage,
        tmp_path / "out",
        source_end_to_end_dir=source,
        expected_commit=_COMMIT,
        max_attempts=1,
        end_to_end_runner=_runner_factory(tmp_path, [True], calls),
        git_context_fn=_clean_git,
    )
    assert result.formal_pass is True
    assert result.status == "RUNTIME_CERTIFIED"
    assert calls[0]["expected_seed"] == 1
    assert calls[0]["horizon"] == 1


def test_second_bounded_attempt_can_recover(tmp_path: Path) -> None:
    triage, source = _triage(tmp_path, "TARGET_HOST_RUNTIME")
    calls = []
    result = execute_bounded_remediation(
        tmp_path,
        triage,
        tmp_path / "out",
        source_end_to_end_dir=source,
        expected_commit=_COMMIT,
        max_attempts=2,
        end_to_end_runner=_runner_factory(
            tmp_path,
            [RuntimeError("temporary failure"), True],
            calls,
        ),
        git_context_fn=_clean_git,
    )
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert result.formal_pass is True
    assert len(report["attempts"]) == 2
    assert report["attempts"][0]["exception"]["type"] == "RuntimeError"


def test_exhaustion_remains_merge_blocked(tmp_path: Path) -> None:
    triage, source = _triage(tmp_path, "MODEL_RUNTIME")
    result = execute_bounded_remediation(
        tmp_path,
        triage,
        tmp_path / "out",
        source_end_to_end_dir=source,
        expected_commit=_COMMIT,
        max_attempts=2,
        end_to_end_runner=_runner_factory(tmp_path, [False, False], []),
        git_context_fn=_clean_git,
    )
    assert result.formal_pass is False
    assert result.status == "REMEDIATION_EXHAUSTED"
    assert result.decision == "MERGE_BLOCKED"


def test_rejects_tampered_triage_evidence(tmp_path: Path) -> None:
    triage, source = _triage(tmp_path, "MODEL_RUNTIME")
    (triage / "REMEDIATION_PLAN.json").write_text("{}", encoding="utf-8")
    assert verify_triage_evidence(triage)["status"] == "FAILED"
    with pytest.raises(ValueError, match="triage evidence verification failed"):
        execute_bounded_remediation(
            tmp_path,
            triage,
            tmp_path / "out",
            source_end_to_end_dir=source,
            expected_commit=_COMMIT,
        )


def test_never_executes_commands_from_triage_plan(tmp_path: Path) -> None:
    triage, source = _triage(tmp_path, "ADMISSION_REJECTED")
    result = execute_bounded_remediation(
        tmp_path,
        triage,
        tmp_path / "out",
        source_end_to_end_dir=source,
        expected_commit=_COMMIT,
        end_to_end_runner=_runner_factory(tmp_path, [False], []),
        git_context_fn=_clean_git,
    )
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["commands_from_triage_executed"] is False
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_writes_deterministic_archive_and_sidecar(tmp_path: Path) -> None:
    triage, source = _triage(tmp_path, "EVIDENCE_INTEGRITY")
    result = execute_bounded_remediation(
        tmp_path,
        triage,
        tmp_path / "out",
        source_end_to_end_dir=source,
        expected_commit=_COMMIT,
        run_id="fixed-run",
        end_to_end_runner=_runner_factory(tmp_path, [False], []),
        git_context_fn=_clean_git,
    )
    expected = result.archive_sha256_path.read_text(encoding="utf-8").split()[0]
    assert expected == _sha256(result.archive_path)
    with zipfile.ZipFile(result.archive_path) as bundle:
        names = bundle.namelist()
    assert "fixed-run/REMEDIATION_EXECUTION_REPORT.json" in names
    assert "fixed-run/SHA256SUMS" in names
