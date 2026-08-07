from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from loto.statsforecast.runtime_lane_end_to_end import run_end_to_end_certification

COMMIT = "a" * 40


def clean_context(_repo: Path) -> dict:
    return {"head": COMMIT, "working_tree_clean": True, "status_porcelain": []}


def fake_target(tmp_path: Path, status: str = "PASS"):
    archive = tmp_path / "result.zip"
    archive.write_bytes(b"zip")
    archive.with_suffix(".zip.sha256").write_text("fake\n", encoding="utf-8")
    return SimpleNamespace(status=status, archive_path=archive)


def test_formal_pass_combines_target_and_admission(tmp_path) -> None:
    def target(*_args, **_kwargs):
        return fake_target(tmp_path)

    def inspect(_archive, **_kwargs):
        return {"status": "ADMITTED", "decision": "RUNTIME_CERTIFIED", "formal_pass": True}

    def write(_report, output_dir):
        output_dir.mkdir(parents=True)
        path = output_dir / "ADMISSION_REPORT.json"
        path.write_text("{}\n", encoding="utf-8")
        return {"json": path}

    result = run_end_to_end_certification(
        tmp_path,
        tmp_path / "out",
        run_id="pass",
        expected_commit=COMMIT,
        git_context_fn=clean_context,
        target_runner=target,
        admission_inspector=inspect,
        admission_writer=write,
    )
    assert result.formal_pass is True
    assert result.decision == "RUNTIME_CERTIFIED"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert (result.output_dir / "SHA256SUMS").is_file()


def test_admission_rejection_blocks_merge(tmp_path) -> None:
    def target(*_args, **_kwargs):
        return fake_target(tmp_path)

    result = run_end_to_end_certification(
        tmp_path,
        tmp_path / "out",
        run_id="reject",
        expected_commit=COMMIT,
        git_context_fn=clean_context,
        target_runner=target,
        admission_inspector=lambda *_args, **_kwargs: {
            "status": "REJECTED",
            "decision": "MERGE_BLOCKED",
            "formal_pass": False,
        },
        admission_writer=lambda _report, output_dir: output_dir.mkdir(parents=True),
    )
    assert result.formal_pass is False
    assert result.decision == "MERGE_BLOCKED"


def test_dirty_worktree_fails_before_target_execution(tmp_path) -> None:
    called = False

    def target(*_args, **_kwargs):
        nonlocal called
        called = True

    result = run_end_to_end_certification(
        tmp_path,
        tmp_path / "out",
        run_id="dirty",
        expected_commit=COMMIT,
        git_context_fn=lambda _repo: {
            "head": COMMIT,
            "working_tree_clean": False,
            "status_porcelain": [" M file.py"],
        },
        target_runner=target,
    )
    assert called is False
    assert result.formal_pass is False
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert "working tree is not clean" in report["failures"]


def test_commit_mismatch_fails_before_target_execution(tmp_path) -> None:
    result = run_end_to_end_certification(
        tmp_path,
        tmp_path / "out",
        run_id="mismatch",
        expected_commit="b" * 40,
        git_context_fn=clean_context,
        target_runner=lambda *_args, **_kwargs: pytest.fail("must not run"),
    )
    assert result.formal_pass is False
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert any("Git HEAD mismatch" in item for item in report["failures"])


def test_target_exception_is_preserved(tmp_path) -> None:
    def target(*_args, **_kwargs):
        raise RuntimeError("network unavailable")

    result = run_end_to_end_certification(
        tmp_path,
        tmp_path / "out",
        run_id="exception",
        expected_commit=COMMIT,
        git_context_fn=clean_context,
        target_runner=target,
    )
    assert result.formal_pass is False
    assert (result.output_dir / "END_TO_END_EXCEPTION.json").is_file()
    assert (result.output_dir / "SHA256SUMS").is_file()


def test_prepare_and_offline_are_mutually_exclusive(tmp_path) -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        run_end_to_end_certification(
            tmp_path,
            tmp_path / "out",
            wheelhouse=tmp_path / "wheels",
            prepare_offline=True,
            offline=True,
        )


def test_wheelhouse_is_required_for_offline_modes(tmp_path) -> None:
    with pytest.raises(ValueError, match="wheelhouse is required"):
        run_end_to_end_certification(
            tmp_path,
            tmp_path / "out",
            offline=True,
        )


def test_existing_run_directory_is_rejected(tmp_path) -> None:
    output_root = tmp_path / "out"
    (output_root / "duplicate").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        run_end_to_end_certification(
            tmp_path,
            output_root,
            run_id="duplicate",
        )
