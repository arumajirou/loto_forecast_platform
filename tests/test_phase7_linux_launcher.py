from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "tools" / "phase7.sh"
REQUIREMENTS = REPO / "tools" / "phase7_holdout_runner" / "linux-runtime-requirements.txt"


def test_linux_launcher_bash_syntax() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    result = subprocess.run(
        [bash, "-n", str(LAUNCHER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_linux_launcher_uses_explicit_evidence_root_without_broad_scan() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "PHASE7_EVIDENCE_ROOT" in text
    assert "/mnt/e/env/ts/phase7_evidence" in text
    assert 'find "$HOME"' not in text
    assert "find /mnt" not in text
    assert "EXPECTED_RUNNER_SHA" in text
    assert "EXPECTED_FREEZE_SHA" in text
    assert "EXPECTED_DEV_SHA" in text
    assert "EXPECTED_CANONICAL_SHA" in text


def test_linux_holdout_requires_current_replay_certificate() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "replay_cert_valid" in text
    assert "ACTION=AUTO_REPLAY_BEFORE_HOLDOUT" in text
    assert "run_replay" in text
    assert "--stop-after-replay" in text
    assert "verification_trial_count" in text
    assert "ALL_80_TRIALS_REPLAYED=PASS" in text


def test_linux_holdout_has_live_progress_and_fail_closed_rerun_message() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "Holdout=$done/50 Actuals=$actuals/50" in text
    assert "RUNNER_TERMINAL_STATE" in text
    assert "do not rerun if terminal state reports locks or actual access" in text
    assert "sealed_holdout_execution.py" in text


def test_linux_runtime_versions_are_pinned() -> None:
    expected = {
        "mlforecast==1.1.0",
        "optuna==4.9.0",
        "catboost==1.2.10",
        "pandas==2.3.3",
        "numpy==2.5.2",
        "scikit-learn==1.9.0",
    }
    actual = {
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert actual == expected


def test_linux_launcher_does_not_change_scientific_selection() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "SCIENTIFIC_GIT_COMMIT" in text
    assert "179bcbc9a51a60f0badfe7faa25f3818ab686229" in text
    assert "8077ccf023f9100344206f588dadae655eb828f3529c4d4d83ebf89c9c1ee074" in text
    assert "deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c" in text
