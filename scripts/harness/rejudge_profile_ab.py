#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

MINIMUM_ACHIEVEMENT_RATE = 0.80
CRITICAL_TASK_FLOORS: dict[str, float] = {
    "instruction": 1.00,
    "reasoning": 0.80,
    "coding": 0.80,
    "long_context": 0.80,
    "structured": 0.80,
    "tools": 0.80,
}


def _latency(task: dict[str, Any]) -> float:
    value = task.get("median_latency_seconds")
    return float(value) if value is not None else float("inf")


def _mode_rank(mode: str, result: dict[str, Any]) -> tuple[Any, ...]:
    tasks = result.get("tasks", {})
    rates = [float(task.get("success_rate", 0.0)) for task in tasks.values()]
    total_latency = sum(_latency(task) for task in tasks.values())
    completion_tokens = sum(int(task.get("completion_tokens", 0)) for task in tasks.values())
    return (
        float(result.get("achievement_rate", 0.0)),
        min(rates, default=0.0),
        float(result.get("stability_score", 0.0)),
        -total_latency,
        -completion_tokens,
        1 if mode == "generic" else 0,
    )


def _recommend(task_name: str, results: dict[str, Any]) -> str | None:
    floor = CRITICAL_TASK_FLOORS.get(task_name, 0.80)
    eligible = {
        mode: result
        for mode, result in results.items()
        if float(result.get("tasks", {}).get(task_name, {}).get("success_rate", 0.0)) >= floor
    }
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda mode: (
            float(eligible[mode]["tasks"][task_name].get("success_rate", 0.0)),
            -_latency(eligible[mode]["tasks"][task_name]),
            -int(eligible[mode]["tasks"][task_name].get("completion_tokens", 0)),
            1 if mode == "generic" else 0,
        ),
    )


def rejudge(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results", {})
    tasks = sorted(
        {task_name for result in results.values() for task_name in result.get("tasks", {})}
    )
    mode_judgments: dict[str, Any] = {}
    eligible_modes: list[str] = []
    for mode, result in results.items():
        failed = [
            task_name
            for task_name in tasks
            if float(result.get("tasks", {}).get(task_name, {}).get("success_rate", 0.0))
            < CRITICAL_TASK_FLOORS.get(task_name, 0.80)
        ]
        achievement = float(result.get("achievement_rate", 0.0))
        eligible = achievement >= MINIMUM_ACHIEVEMENT_RATE and not failed
        if eligible:
            eligible_modes.append(mode)
        mode_judgments[mode] = {
            "achievement_rate": achievement,
            "failed_critical_tasks": failed,
            "critical_tasks_meet_floor": not failed,
            "eligible": eligible,
        }

    best_observed_mode = (
        max(results, key=lambda mode: _mode_rank(mode, results[mode])) if results else None
    )
    best_mode = (
        max(eligible_modes, key=lambda mode: _mode_rank(mode, results[mode]))
        if eligible_modes
        else None
    )
    generic_rate = float(results.get("generic", {}).get("achievement_rate", -1.0))
    candidate_beats_generic = bool(
        best_mode
        and best_mode != "generic"
        and float(results[best_mode].get("achievement_rate", 0.0)) > generic_rate
    )
    return {
        "judgment_version": "profile-ab-strict-v2",
        "source_model": data.get("model"),
        "source_profile_id": data.get("profile_id"),
        "minimum_achievement_rate": MINIMUM_ACHIEVEMENT_RATE,
        "critical_task_floors": CRITICAL_TASK_FLOORS,
        "mode_judgments": mode_judgments,
        "best_observed_mode": best_observed_mode,
        "best_mode": best_mode,
        "eligible_modes": eligible_modes,
        "candidate_beats_generic": candidate_beats_generic,
        "best_mode_meets_gate": bool(best_mode and best_mode in eligible_modes),
        "recommended_mode_by_task": {
            task_name: _recommend(task_name, results) for task_name in tasks
        },
        "automatic_promotion_allowed": False,
        "human_approval_required": True,
        "limitations": [
            "legacy reports do not contain per-trial response excerpts",
            "reasoning correctness versus format cannot be reconstructed without rerun",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    payload = {
        "source_report": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "strict_judgment": rejudge(data),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output}\n",
        encoding="utf-8",
    )
    print(f"report={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
