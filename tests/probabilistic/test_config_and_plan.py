from __future__ import annotations

from pathlib import Path

from loto.probabilistic.config import load_run_config, stable_hash
from loto.probabilistic.planner import build_plan, plan_summary


def test_smoke_plan_has_one_runnable_reference_trial_per_model() -> None:
    config = load_run_config(Path("configs/probabilistic/smoke.yaml"))
    plan = build_plan(config)
    assert len(plan) == 73
    assert all(item.allowed for item in plan)
    assert {item.backend for item in plan} == {"builtin"}
    assert len({item.model_id for item in plan}) == 73
    assert plan_summary(config)["trials_allowed"] == 73


def test_hash_is_order_stable() -> None:
    assert stable_hash({"a": 1, "b": [2, 3]}) == stable_hash({"b": [2, 3], "a": 1})
