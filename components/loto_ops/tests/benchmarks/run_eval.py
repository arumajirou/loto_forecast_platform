"""Benchmark task runner for Inspect AI evaluation.

Reads development_tasks.json and creates Inspect AI Task definitions.
Each task is scored using match or custom_scorer from inspect_bridge.

Usage:
    pip install inspect-ai
    inspect eval tests/benchmarks/run_eval.py --model hermes_gateway

    Or directly:
    python3 -m pytest tests/benchmarks/run_eval.py -v
"""

import json
from pathlib import Path
from typing import Any

from loto_ops.benchmarks.inspect_bridge import custom_scorer, match_score

# Path to development tasks
TASKS_FILE = Path("/mnt/e/env/ts/shared-ai-memory/benchmarks/development_tasks.json")


def load_tasks() -> list[dict[str, Any]]:
    """Load development tasks from JSON file."""
    if not TASKS_FILE.exists():
        # Create a sample task if file doesn't exist
        sample_tasks = [
            {
                "id": "task_001",
                "description": "Basic arithmetic operation",
                "input": "Calculate 2 + 2",
                "expected": "4",
                "scorer": "match",
            },
            {
                "id": "task_002",
                "description": "Python code generation",
                "input": "Write a Python function to calculate factorial",
                "expected": ["factorial", "return"],
                "scorer": "custom",
            },
        ]
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TASKS_FILE, "w") as f:
            json.dump(sample_tasks, f, indent=2)
        return sample_tasks

    with open(TASKS_FILE) as f:
        return json.load(f)


def create_task(task: dict[str, Any]) -> dict[str, Any]:
    """Create an Inspect AI Task definition from task data."""
    task_def = {
        "name": task["id"],
        "prompt": f"{task['description']}\n\nInput: {task['input']}",
        "target": task.get("expected", ""),
    }

    # Add scorer
    if task.get("scorer") == "match":
        task_def["scorer"] = match_score
    elif task.get("scorer") == "custom":
        task_def["scorer"] = lambda response: custom_scorer(response, [task["expected"]])

    return task_def


def run_eval() -> list[dict[str, Any]]:
    """Main evaluation function that loads tasks and creates Inspect AI Task definitions."""
    tasks = load_tasks()
    task_definitions = []

    for task in tasks:
        task_def = create_task(task)
        task_definitions.append(task_def)

    return task_definitions


if __name__ == "__main__":
    # For direct testing
    tasks = run_eval()
    print(f"Loaded {len(tasks)} tasks:")
    for task in tasks:
        print(f"  - {task['name']}: {task['prompt'][:50]}...")
