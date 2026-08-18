from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "runtime_audit" / "taj19_gpu_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("taj19_gpu_preflight_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plan() -> dict:
    return {
        "tasks": [
            {"model_id": "cpu-model", "game": "g1", "resource_class": "CPU"},
            {"model_id": "gpu-model", "game": "g1", "resource_class": "GPU"},
        ]
    }


def test_gpu_preflight_accepts_positive_gpu_capacity() -> None:
    module = load_module()
    result = module.validate_resource_preflight(
        _plan(),
        {"gpu_count": 1, "gpu_total_mib": [16303], "gpu_free_mib": [12000]},
        {
            "parallel_gpu_models": 1,
            "gpu_device_slots": [1],
            "gpu_slot_mib": 5120,
            "safety_margin_mib": 2048,
        },
    )
    assert result["status"] == "PASS"
    assert result["gpu_resource_task_count"] == 1
    assert result["required_free_mib_per_slot"] == 7168


def test_gpu_preflight_blocks_zero_admitted_slots() -> None:
    module = load_module()
    with pytest.raises(module.GPUPreflightError, match="GPU_CAPACITY_NOT_READY"):
        module.validate_resource_preflight(
            _plan(),
            {"gpu_count": 1, "gpu_total_mib": [16303], "gpu_free_mib": [6000]},
            {
                "parallel_gpu_models": 0,
                "gpu_device_slots": [0],
                "gpu_slot_mib": 5120,
                "safety_margin_mib": 2048,
            },
        )


def test_gpu_preflight_blocks_missing_gpu_hardware_for_gpu_tasks() -> None:
    module = load_module()
    with pytest.raises(module.GPUPreflightError, match="GPU_CAPACITY_NOT_READY"):
        module.validate_resource_preflight(
            _plan(),
            {"gpu_count": 0, "gpu_total_mib": [], "gpu_free_mib": []},
            {
                "parallel_gpu_models": 0,
                "gpu_device_slots": [],
                "gpu_slot_mib": 5120,
                "safety_margin_mib": 2048,
            },
        )


def test_gpu_preflight_allows_cpu_only_matrix_without_gpu() -> None:
    module = load_module()
    result = module.validate_resource_preflight(
        {"tasks": [{"model_id": "cpu", "game": "g1", "resource_class": "CPU"}]},
        {"gpu_count": 0, "gpu_total_mib": [], "gpu_free_mib": []},
        {
            "parallel_gpu_models": 0,
            "gpu_device_slots": [],
            "gpu_slot_mib": 5120,
            "safety_margin_mib": 2048,
        },
    )
    assert result["status"] == "PASS"
    assert result["gpu_resource_task_count"] == 0
