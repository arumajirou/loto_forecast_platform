from __future__ import annotations

from importlib import util
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "harness"
    / "rejudge_profile_ab.py"
)
SPEC = util.spec_from_file_location("rejudge_profile_ab", SCRIPT)
assert SPEC and SPEC.loader
MODULE = util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_rejudge_rejects_zero_reasoning_and_prefers_generic_on_tie() -> None:
    tasks = {
        "instruction": {"success_rate": 1.0, "median_latency_seconds": 1.0, "completion_tokens": 1},
        "reasoning": {"success_rate": 0.0, "median_latency_seconds": 1.0, "completion_tokens": 1},
        "coding": {"success_rate": 1.0, "median_latency_seconds": 1.0, "completion_tokens": 1},
    }
    data = {
        "model": "qwen3-test",
        "profile_id": "qwen3",
        "results": {
            "generic": {"achievement_rate": 0.8, "stability_score": 0.6, "tasks": tasks},
            "tools": {"achievement_rate": 0.8, "stability_score": 0.6, "tasks": tasks},
        },
    }
    judgment = MODULE.rejudge(data)
    assert judgment["best_observed_mode"] == "generic"
    assert judgment["best_mode"] is None
    assert judgment["eligible_modes"] == []
    assert judgment["best_mode_meets_gate"] is False
    assert judgment["recommended_mode_by_task"]["reasoning"] is None
