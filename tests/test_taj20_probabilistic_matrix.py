from __future__ import annotations

from pathlib import Path

from scripts.run_taj20_probabilistic_matrix import (
    EXPECTED_GAMES,
    EXPECTED_PAIRS,
    EXPECTED_PROBABILISTIC_MODELS,
    build_matrix_plan,
)


def test_taj20_plan_is_exact_76_by_6(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_taj20_probabilistic_matrix._git_head", lambda: "a" * 40)
    plan = build_matrix_plan(campaign_id="test-taj20", root=tmp_path, seed=1)
    assert plan["models"] == EXPECTED_PROBABILISTIC_MODELS
    assert len(plan["games"]) == EXPECTED_GAMES
    assert len(plan["tasks"]) == EXPECTED_PAIRS
    assert len({row["task_key"] for row in plan["tasks"]}) == EXPECTED_PAIRS
    assert len({row["model_id"] for row in plan["tasks"]}) == EXPECTED_PROBABILISTIC_MODELS
    assert {row["game"] for row in plan["tasks"]} == set(plan["games"])
    assert {row["seed"] for row in plan["tasks"]} == {1}
    assert plan["backend_policy"] == "primary_native"
    assert plan["scientific_boundary"]["holdout"] == "CLOSED"
    assert plan["scientific_boundary"]["prospective"] == "CLOSED"


def test_taj20_plan_preserves_blocked_game_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_taj20_probabilistic_matrix._git_head", lambda: "b" * 40)
    plan = build_matrix_plan(campaign_id="test-taj20", root=tmp_path, seed=1)
    blocked = [row for row in plan["tasks"] if not row["allowed"]]
    assert blocked
    assert all(row["game"] for row in blocked)
    assert all("::" in row["task_key"] for row in blocked)
