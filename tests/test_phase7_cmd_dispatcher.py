from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DISPATCHER = REPO / "tools" / "phase7.cmd"


def test_phase7_dispatcher_does_not_forward_mode_argument() -> None:
    text = DISPATCHER.read_text(encoding="utf-8")

    assert 'if /I "%~1"=="forensic" goto :forensic' in text
    assert 'if /I "%~1"=="live" goto :live' in text
    assert 'if /I "%~1"=="replay" goto :replay' in text
    assert 'call "%~dp0phase7_holdout_runner\\run_frozen_config_forensics.cmd"' in text
    assert 'call "%~dp0phase7_holdout_runner\\run_pr355_live_mapping_diagnostic.cmd"' in text
    assert 'call "%~dp0phase7_holdout_runner\\run_pr355_replay_only.cmd"' in text
    assert 'run_frozen_config_forensics.cmd" %*' not in text
    assert 'run_pr355_live_mapping_diagnostic.cmd" %*' not in text
    assert 'run_pr355_replay_only.cmd" %*' not in text
