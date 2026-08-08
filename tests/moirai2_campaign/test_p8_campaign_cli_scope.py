from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_campaign_cli_is_serial_and_calls_existing_p8_certifier() -> None:
    text = (ROOT / "scripts" / "run_moirai2_runtime_campaign.py").read_text(encoding="utf-8")
    assert '"execution_policy": "strictly_serial"' in text
    assert '"parallel_case_count": 1' in text
    assert "certify_moirai2_runtime.py" in text
    assert "FORMAL_CASE_NAMES" in text
    assert "formal_runtime_certified" in text


def test_preflight_cli_requires_lock_and_frozen_probe() -> None:
    text = (ROOT / "scripts" / "preflight_moirai2_runtime_lane.py").read_text(encoding="utf-8")
    assert "validate_lane_files" in text
    assert "run_frozen_probe" in text
    assert "--snapshot-path" in text
    assert "--runtime-lane" in text
