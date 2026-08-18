from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class GPUPreflightError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GPUPreflightError(f"required JSON missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GPUPreflightError(f"JSON root must be an object: {path}")
    return payload


def validate_resource_preflight(
    matrix_plan: dict[str, Any],
    snapshot: dict[str, Any],
    resource_plan: dict[str, Any],
) -> dict[str, Any]:
    tasks = matrix_plan.get("tasks")
    if not isinstance(tasks, list):
        raise GPUPreflightError("MATRIX_PLAN.tasks must be a list")

    gpu_resource_tasks = [
        task
        for task in tasks
        if isinstance(task, dict) and str(task.get("resource_class", "CPU")) != "CPU"
    ]
    gpu_count = int(snapshot.get("gpu_count", 0) or 0)
    totals = [int(value) for value in snapshot.get("gpu_total_mib", [])]
    frees = [int(value) for value in snapshot.get("gpu_free_mib", [])]
    slots = [int(value) for value in resource_plan.get("gpu_device_slots", [])]
    parallel_gpu_models = int(resource_plan.get("parallel_gpu_models", 0) or 0)
    gpu_slot_mib = int(resource_plan.get("gpu_slot_mib", 0) or 0)
    safety_margin_mib = int(resource_plan.get("safety_margin_mib", 0) or 0)
    required_free_mib = gpu_slot_mib + safety_margin_mib

    result = {
        "status": "PASS",
        "gpu_resource_task_count": len(gpu_resource_tasks),
        "gpu_count": gpu_count,
        "gpu_total_mib": totals,
        "gpu_free_mib": frees,
        "gpu_device_slots": slots,
        "parallel_gpu_models": parallel_gpu_models,
        "gpu_slot_mib": gpu_slot_mib,
        "safety_margin_mib": safety_margin_mib,
        "required_free_mib_per_slot": required_free_mib,
    }

    if gpu_resource_tasks and (
        gpu_count < 1
        or parallel_gpu_models < 1
        or sum(slots) < 1
        or not frees
        or max(frees) < required_free_mib
    ):
        result["status"] = "BLOCKED"
        raise GPUPreflightError(
            "GPU_CAPACITY_NOT_READY: "
            f"gpu_tasks={len(gpu_resource_tasks)} gpu_count={gpu_count} "
            f"gpu_free_mib={frees} gpu_device_slots={slots} "
            f"parallel_gpu_models={parallel_gpu_models} "
            f"required_free_mib_per_slot={required_free_mib}"
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAJ-19 fail-closed GPU capacity preflight")
    parser.add_argument("--root", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    try:
        result = validate_resource_preflight(
            read_json(root / "MATRIX_PLAN.json"),
            read_json(root / "RESOURCE_SNAPSHOT.json"),
            read_json(root / "RESOURCE_PLAN.json"),
        )
    except GPUPreflightError as exc:
        print("TAJ19_GPU_PREFLIGHT=BLOCKED")
        print(f"REASON={exc}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        return 20

    print("TAJ19_GPU_PREFLIGHT=PASS")
    print(f"GPU_RESOURCE_TASKS={result['gpu_resource_task_count']}")
    print(f"GPU_COUNT={result['gpu_count']}")
    print(f"GPU_TOTAL_MIB={','.join(map(str, result['gpu_total_mib']))}")
    print(f"GPU_FREE_MIB={','.join(map(str, result['gpu_free_mib']))}")
    print(f"GPU_DEVICE_SLOTS={','.join(map(str, result['gpu_device_slots']))}")
    print(f"PARALLEL_GPU_MODELS={result['parallel_gpu_models']}")
    print(f"GPU_SLOT_MIB={result['gpu_slot_mib']}")
    print(f"GPU_SAFETY_MARGIN_MIB={result['safety_margin_mib']}")
    print(f"GPU_REQUIRED_FREE_MIB_PER_SLOT={result['required_free_mib_per_slot']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
