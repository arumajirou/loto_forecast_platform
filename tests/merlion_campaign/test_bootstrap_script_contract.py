from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_inner_bootstrap_supports_immutable_preflight_reuse() -> None:
    script = (ROOT / "scripts/bootstrap_merlion_core_env.sh").read_text(encoding="utf-8")
    assert 'PREFLIGHT_MODE="${MERLION_PREFLIGHT_MODE:-GENERATE}"' in script
    assert "REUSE)" in script
    assert "verify_merlion_bootstrap_lineage.py" in script
    assert '--output "${PREFLIGHT_PATH}"' in script


def test_resume_runner_binds_and_rechecks_preflight_bytes() -> None:
    script = (ROOT / "scripts/resume_merlion_core_bootstrap.sh").read_text(encoding="utf-8")
    assert "PREFLIGHT_FILE_SHA_BEFORE" in script
    assert "PREFLIGHT_FILE_SHA_AFTER" in script
    assert "MERLION_PREFLIGHT_MODE=REUSE" in script
    assert "MERLION_PREFLIGHT_REPORT_SHA256" in script
    assert 'write_failure "preflight_lineage_mutated" 73' in script


def test_packaging_failure_is_separate_from_bootstrap_failure() -> None:
    script = (ROOT / "scripts/resume_merlion_core_bootstrap.sh").read_text(encoding="utf-8")
    assert "EVIDENCE_PACKAGING_FAILURE.json" in script
    assert "merlion-evidence-packaging-failure-v1" in script
    assert "PACKAGING_FAILURE_EXIT=70" in script
    assert '"bootstrap_exit_code": int(sys.argv[3])' in script
    assert '"packaging_exit_code": int(sys.argv[4])' in script
