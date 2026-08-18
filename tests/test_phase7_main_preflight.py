from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "tools" / "phase7_holdout_runner" / "main_preflight.py"
SPEC = importlib.util.spec_from_file_location("phase7_main_preflight", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_require_zero_progress_accepts_replay_verification_only() -> None:
    progress = {
        "state": "REPLAY_VERIFICATION",
        "holdout_draws_done": 0,
        "actuals_accessed": 0,
    }
    assert MOD.require_zero_progress(progress) == "REPLAY_VERIFICATION"


@pytest.mark.parametrize(
    "progress",
    [
        {"state": "HOLDOUT", "holdout_draws_done": 0, "actuals_accessed": 0},
        {
            "state": "REPLAY_VERIFICATION",
            "holdout_draws_done": 1,
            "actuals_accessed": 0,
        },
        {
            "state": "REPLAY_VERIFICATION",
            "holdout_draws_done": 0,
            "actuals_accessed": 1,
        },
    ],
)
def test_require_zero_progress_fails_closed(progress: dict[str, object]) -> None:
    with pytest.raises(MOD.PreflightError):
        MOD.require_zero_progress(progress)


def test_preflight_does_not_execute_holdout_runner() -> None:
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "--stop-after-replay" not in text
    assert "prediction_locks" in text
    assert '"holdout_executed": False' in text
    assert '"prediction_lock_created": False' in text
    assert '"safe_to_read_actuals_before_prediction_lock": False' in text
