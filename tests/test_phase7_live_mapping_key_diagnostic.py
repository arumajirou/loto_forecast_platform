from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "tools" / "phase7_holdout_runner" / "live_mapping_key_diagnostic.py"
SPEC = importlib.util.spec_from_file_location("phase7_live_mapping_key_diagnostic", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_diagnostic_runner_is_written_beside_derived_semantic_module(tmp_path: Path) -> None:
    bundle = tmp_path / "derived_bundle"
    assert MOD.diagnostic_runner_path(bundle) == (bundle / "phase7_holdout_mapping_diagnostic.py")


def test_collect_non_string_mapping_keys_reports_typed_path() -> None:
    config = {
        "mlf_init_params": {
            "lag_transforms": {
                1: ["rolling"],
            },
        },
    }

    assert MOD.collect_non_string_mapping_keys(config) == [
        {
            "mapping_path": '$["mlf_init_params"]["lag_transforms"]',
            "key_type": "int",
            "key_repr": "1",
            "value_type": "list",
        }
    ]


def test_collect_non_string_mapping_keys_preserves_string_numeric_key() -> None:
    config = {
        "mlf_init_params": {
            "lag_transforms": {
                "1": ["rolling"],
            },
        },
    }

    assert MOD.collect_non_string_mapping_keys(config) == []


def test_patch_runner_inserts_diagnostic_before_canonical_hash() -> None:
    source = """def replay(seed, best_config, replay_dir, legacy_object_states):
    canonical_replay_hash = (
        canonical_semantic_sha256_v1(
            best_config,
            legacy_object_states=
                legacy_object_states,
        )
    )
    return canonical_replay_hash
"""

    patched = MOD.patch_runner_for_mapping_diagnostic(source)

    assert "MAPPING_KEY_DIAGNOSTIC.json" in patched
    assert "live best_config non-string mapping key" in patched
    assert patched.index("mapping_key_findings") < patched.index("canonical_replay_hash")
    compile(patched, "diagnostic.py", "exec")


def test_patch_runner_fails_closed_when_anchor_missing() -> None:
    with pytest.raises(MOD.DiagnosticError, match="anchor count=0"):
        MOD.patch_runner_for_mapping_diagnostic("print('x')\n")
