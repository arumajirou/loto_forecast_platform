from __future__ import annotations

import sys

from loto.orchestration.process_observer import run_monitored_process


def test_monitored_process_records_child_pid_tree_and_stdout(tmp_path) -> None:
    result = run_monitored_process(
        [
            sys.executable,
            "-c",
            "import time; print('ready', flush=True); time.sleep(0.15)",
        ],
        cwd=tmp_path,
        timeout=5,
        poll_interval=0.05,
    )

    assert result.returncode == 0
    assert result.timed_out is False
    assert "ready" in result.stdout
    assert result.observation.child_pid > 0
    assert any(node.pid == result.observation.child_pid for node in result.observation.process_tree)
    assert result.observation.sample_count >= 1
    assert result.observation.ended_at >= result.observation.started_at


def test_monitored_process_preserves_nonzero_exit_and_stderr(tmp_path) -> None:
    result = run_monitored_process(
        [
            sys.executable,
            "-c",
            "import sys; print('failure', file=sys.stderr); raise SystemExit(7)",
        ],
        cwd=tmp_path,
        timeout=5,
        poll_interval=0.05,
    )

    assert result.returncode == 7
    assert result.timed_out is False
    assert "failure" in result.stderr
    assert result.observation.child_pid > 0
    assert result.observation.returncode == 7


def test_monitored_process_timeout_retains_evidence(tmp_path) -> None:
    result = run_monitored_process(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        timeout=0.2,
        poll_interval=0.05,
    )

    assert result.timed_out is True
    assert result.observation.timed_out is True
    assert result.observation.child_pid > 0
    assert any(node.pid == result.observation.child_pid for node in result.observation.process_tree)
    assert result.observation.ended_at >= result.observation.started_at
