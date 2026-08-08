from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_evidence_cli_is_read_only_and_fail_closed() -> None:
    text = (ROOT / "scripts" / "verify_moirai2_runtime_evidence.py").read_text(encoding="utf-8")
    assert "--supported-campaign-dir" in text
    assert "--cuda-campaign-dir" in text
    assert "--expected-source-commit" in text
    assert "P8C_RUNTIME_EVIDENCE_REPORT.json" in text
    assert '"p9_oof_gate_open": False' in text
    assert "verify_runtime_evidence_pair" in text


def test_source_identity_cli_requires_clean_git_evidence() -> None:
    text = (ROOT / "scripts" / "capture_moirai2_source_identity.py").read_text(encoding="utf-8")
    assert "capture_source_identity" in text
    assert "run_moirai2_provider.py" in text
    assert "runtime_evidence_gate.py" in text
