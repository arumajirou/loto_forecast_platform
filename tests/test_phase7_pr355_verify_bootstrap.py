from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "tools" / "phase7_holdout_runner" / "pr355_verify_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("phase7_pr355_verify_bootstrap", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_verify_bootstrap_pins_current_scientific_blobs() -> None:
    assert MOD.EXPECTED_CRITICAL_BLOBS == {
        "src/loto/evaluation/semantic_config.py": "257d4d4a88e56f6070200a67fd86b2beca73a3c1",
        "tools/phase7_holdout_runner/derive_canonical_runner.py": "efa988d671cb31820d4a4292498dd034c85ce481",
    }


def test_verify_bootstrap_checks_focused_tests_and_ruff_files() -> None:
    assert "tests/evaluation/test_semantic_config.py" in MOD.TEST_FILES
    assert "tests/test_phase7_holdout_runner_derivation.py" in MOD.TEST_FILES
    assert "tests/test_phase7_frozen_config_forensics.py" in MOD.TEST_FILES
    assert "tests/test_phase7_live_mapping_key_diagnostic.py" in MOD.TEST_FILES
    assert "src/loto/evaluation/semantic_config.py" in MOD.RUFF_FILES
    assert "tools/phase7_holdout_runner/derive_canonical_runner.py" in MOD.RUFF_FILES


def test_verify_bootstrap_avoids_full_checkout() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "git worktree" not in source
    assert "git checkout" not in source
    assert "git reset" not in source
    assert "git clean" not in source
