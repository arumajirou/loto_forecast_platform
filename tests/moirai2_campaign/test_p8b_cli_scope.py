from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_candidate_cli_is_non_destructive_and_uses_uv_lock() -> None:
    source = (ROOT / "scripts" / "generate_moirai2_lock_candidate.py").read_text(
        encoding="utf-8"
    )
    assert '"lock", "--project"' in source
    assert "candidate-project" in source
    assert '"lane_modified": False' in source
    assert "exist_ok=False" in source


def test_install_cli_requires_explicit_approval_guards() -> None:
    source = (ROOT / "scripts" / "install_reviewed_moirai2_lock.py").read_text(
        encoding="utf-8"
    )
    assert "APPLY-REVIEWED-MOIRAI2-LOCK" in source
    assert "--expected-lock-sha256" in source
    assert "--output-dir" in source
    assert "--reviewer" in source
    assert "--reviewed-at" in source
    assert "--apply" in source
    assert "--replace-existing-sha256" in source


def test_runtime_preflight_requires_installed_review() -> None:
    source = (
        ROOT / "src" / "loto" / "moirai2_campaign" / "runtime_preflight.py"
    ).read_text(encoding="utf-8")
    assert "validate_installed_review" in source
    assert "reviewed lock validation failed" in source
    assert "runtime_lane=runtime_lane" in source


def test_campaign_passes_runtime_lane_to_preflight() -> None:
    source = (ROOT / "scripts" / "run_moirai2_runtime_campaign.py").read_text(
        encoding="utf-8"
    )
    assert "runtime_lane=arguments.runtime_lane" in source
    assert "validate_lane_files" in source
