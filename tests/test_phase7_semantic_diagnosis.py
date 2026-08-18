from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "phase7_semantic_diagnosis" / "semantic_diagnosis.py"
SPEC = importlib.util.spec_from_file_location("phase7_semantic_diagnosis", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_normalize_object_repr_removes_memory_address() -> None:
    left = {"transform": "<pkg.Transform object at 0x1234ABCD>"}
    right = {"transform": "<pkg.Transform object at 0xDEADBEEF>"}

    assert MOD.normalize_serialized(left) == MOD.normalize_serialized(right)


def test_representation_only_requires_same_object_class() -> None:
    same_class = {
        "kind": "VALUE",
        "left": "<pkg.Transform object at 0x1234>",
        "right": "<pkg.Transform object at 0x5678>",
    }
    different_class = {
        "kind": "VALUE",
        "left": "<pkg.TransformA object at 0x1234>",
        "right": "<pkg.TransformB object at 0x5678>",
    }

    assert MOD.representation_only_diff(same_class) is True
    assert MOD.representation_only_diff(different_class) is False


def test_numeric_diff_policy_uses_tight_tolerance() -> None:
    assert MOD.recursive_diff({"x": 0.3}, {"x": 0.30000000000000004}) == []
    assert MOD.recursive_diff({"x": 0.3}, {"x": 0.31})


def test_frozen_experiment_commit_is_not_current_tool_head_contract() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "EXPECTED_EXPERIMENT_GIT_COMMIT" in source
    assert "repo_head != EXPECTED_EXPERIMENT_GIT_COMMIT" not in source
    assert "merge-base" in source
    assert "--is-ancestor" in source


def test_diagnosis_has_no_canonical_dataset_cli_argument() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert 'add_argument("--canonical"' not in source
    assert 'add_argument("--holdout"' not in source
