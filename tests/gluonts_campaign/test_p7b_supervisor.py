from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest


ENVIRONMENTS = Path(__file__).resolve().parents[2] / "environments"
sys.path.insert(0, str(ENVIRONMENTS))
import gluonts_p7b as supervisor


def test_execute_command_preserves_nonzero_exit(tmp_path: Path) -> None:
    started: list[tuple[int, int, str]] = []
    result = supervisor.execute_command(
        ["bash", "-c", "echo out; echo err >&2; exit 7"],
        {},
        10,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        lambda pid, pgid, stamp: started.append((pid, pgid, stamp)),
        threading.Event(),
    )
    assert result.state == "COMPLETED"
    assert result.return_code == 7
    assert started and started[0][0] == result.process_id
    assert (tmp_path / "stdout.log").read_text().strip() == "out"
    assert (tmp_path / "stderr.log").read_text().strip() == "err"


def test_execute_command_times_out_process_group(tmp_path: Path) -> None:
    result = supervisor.execute_command(
        ["bash", "-c", "sleep 30"],
        {},
        1,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        lambda _pid, _pgid, _stamp: None,
        threading.Event(),
    )
    assert result.state == "TIMED_OUT"
    assert result.return_code == 124
    assert result.errors


def test_completed_stage_is_not_rerun_on_resume(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    marker = tmp_path / "marker"
    source = {
        "repository_root": "/repo",
        "branch": "feature",
        "commit_sha": "a" * 40,
        "tracked_worktree_dirty": False,
        "source_sha256": {"runner.py": "b" * 64},
    }
    journal = supervisor.new_journal("run", output, source)
    journal_path = output / "p7b_execution_journal.json"
    supervisor.write_journal(journal_path, journal)
    first_rc = supervisor.run_stage(
        output,
        journal_path,
        journal,
        "compat_bootstrap",
        ["bash", "-c", "echo first; exit 5"],
        {},
        10,
        threading.Event(),
    )
    assert first_rc == 5
    assert journal["stages"]["compat_bootstrap"]["state"] == "COMPLETED"

    second_rc = supervisor.run_stage(
        output,
        journal_path,
        journal,
        "compat_bootstrap",
        ["bash", "-c", f"touch {marker}"],
        {},
        10,
        threading.Event(),
    )
    assert second_rc == 5
    assert not marker.exists()


def test_resume_detects_completed_output_tamper(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    source = {
        "repository_root": "/repo",
        "branch": "feature",
        "commit_sha": "a" * 40,
        "tracked_worktree_dirty": False,
        "source_sha256": {"runner.py": "b" * 64},
    }
    journal = supervisor.new_journal("run", output, source)
    journal_path = output / "p7b_execution_journal.json"
    supervisor.write_journal(journal_path, journal)
    supervisor.run_stage(
        output,
        journal_path,
        journal,
        "latest_bootstrap",
        ["bash", "-c", "echo original"],
        {},
        10,
        threading.Event(),
    )
    (output / "latest_bootstrap.stdout.log").write_text("tampered\n")
    with pytest.raises(supervisor.ResumeIdentityError, match="identity changed"):
        supervisor.validate_completed_stage(
            output,
            journal["stages"]["latest_bootstrap"],
        )


def test_interrupted_attempt_is_archived_before_retry(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    source = {
        "repository_root": "/repo",
        "branch": "feature",
        "commit_sha": "a" * 40,
        "tracked_worktree_dirty": False,
        "source_sha256": {"runner.py": "b" * 64},
    }
    journal = supervisor.new_journal("run", output, source)
    record = journal["stages"]["audit"]
    record.update(
        {
            "state": "INTERRUPTED",
            "stdout_path": "audit.stdout.log",
            "stderr_path": "audit.stderr.log",
            "return_code_path": "audit.rc",
            "artifact_root": "audit",
            "ended_at_utc": supervisor.utc_now(),
            "errors": ["interrupted"],
        }
    )
    (output / "audit.stdout.log").write_text("partial\n")
    (output / "audit.stderr.log").write_text("")
    (output / "audit.rc").write_text("130\n")
    (output / "audit").mkdir()
    (output / "audit/partial.json").write_text("{}\n")
    supervisor.archive_interrupted_stage(output, record)
    history = list((output / "history").iterdir())
    assert len(history) == 1
    assert (history[0] / "audit.stdout.log").is_file()
    assert (history[0] / "audit").is_dir()


def test_execution_checksum_inventory_rejects_extra_file(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    (output / "a.txt").write_text("a\n")
    supervisor.write_execution_checksums(output)
    supervisor.verify_checksum_file(output, "P7B_EXECUTION_SHA256SUMS")
    (output / "extra.txt").write_text("extra\n")
    with pytest.raises(supervisor.ResumeIdentityError, match="inventory mismatch"):
        supervisor.verify_checksum_file(output, "P7B_EXECUTION_SHA256SUMS")


def test_partial_checksum_is_archived_before_resume(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    (output / "p7b_execution_journal.json").write_text("{}\n")
    (output / "partial.log").write_text("partial\n")
    supervisor.write_partial_checksums(output)
    supervisor.archive_partial_resume_state(output, 1)
    assert not (output / "P7B_PARTIAL_SHA256SUMS").exists()
    history = list((output / "history").iterdir())
    assert len(history) == 1
    assert (history[0] / "P7B_PARTIAL_SHA256SUMS").is_file()
    assert (history[0] / "journal.json").is_file()


def test_new_journal_matches_pydantic_contract(tmp_path: Path) -> None:
    from loto.adapters.gluonts.p7b_contract import P7BExecutionJournal

    output = tmp_path / "run"
    source = {
        "repository_root": "/repo",
        "branch": "feature",
        "commit_sha": "a" * 40,
        "tracked_worktree_dirty": False,
        "source_sha256": {"runner.py": "b" * 64},
    }
    journal = supervisor.new_journal("run", output, source)
    validated = P7BExecutionJournal.model_validate(journal)
    assert validated.run_id == "run"


def test_command_interruption_is_recorded(tmp_path: Path) -> None:
    interrupted = threading.Event()
    interrupted.set()
    result = supervisor.execute_command(
        ["bash", "-c", "sleep 30"],
        {},
        30,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        lambda _pid, _pgid, _stamp: None,
        interrupted,
    )
    assert result.state == "INTERRUPTED"
    assert result.errors == ["execution interrupted by signal"]
