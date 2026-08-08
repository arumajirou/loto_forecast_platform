from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import OBSERVED_AT, observation_from_bytes

from loto.clock_health import (
    evaluate_clock_health,
    verify_evidence_bundle,
    write_evidence_bundle,
)


def test_evidence_bundle_round_trip(
    tmp_path: Path,
    policy,
    tracking_bytes,
    sources_bytes,
) -> None:
    observation = observation_from_bytes(policy, tracking_bytes, sources_bytes)
    decision = evaluate_clock_health(
        observation,
        policy,
        decision_id="bundle-decision-v1",
        evaluated_at_utc=OBSERVED_AT,
    )
    output = tmp_path / "bundle"
    write_evidence_bundle(
        output,
        observation=observation,
        decision=decision,
        policy=policy,
        tracking_stdout=tracking_bytes,
        sources_stdout=sources_bytes,
    )
    verify_evidence_bundle(output)
    assert (output / "ARTIFACT_MANIFEST.json").is_file()
    assert (output / "SHA256SUMS").is_file()


def test_evidence_bundle_tamper_is_rejected(
    tmp_path: Path,
    policy,
    tracking_bytes,
    sources_bytes,
) -> None:
    observation = observation_from_bytes(policy, tracking_bytes, sources_bytes)
    decision = evaluate_clock_health(
        observation,
        policy,
        decision_id="tamper-decision-v1",
        evaluated_at_utc=OBSERVED_AT,
    )
    output = tmp_path / "bundle"
    write_evidence_bundle(
        output,
        observation=observation,
        decision=decision,
        policy=policy,
        tracking_stdout=tracking_bytes,
        sources_stdout=sources_bytes,
    )
    (output / "chronyc_tracking.txt").write_bytes(tracking_bytes + b"tamper")
    with pytest.raises(ValueError, match="artifact mismatch"):
        verify_evidence_bundle(output)


def test_cli_files_mode_smoke(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    output = tmp_path / "cli-output"
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run_clock_health_check.py"),
            "--mode",
            "files",
            "--policy",
            str(root / "configs" / "clock_health" / "default_policy.json"),
            "--output-dir",
            str(output),
            "--tracking-file",
            str(Path(__file__).parent / "fixtures" / "healthy_tracking.txt"),
            "--sources-file",
            str(Path(__file__).parent / "fixtures" / "healthy_sources.txt"),
            "--observed-at-utc",
            "2026-08-06T09:00:00Z",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "HEALTHY"
    assert payload["prediction_lock_allowed"] is True
    assert payload["external_trust_established"] is False
    verify_evidence_bundle(output)


def test_cli_malformed_input_fails_closed(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    malformed = tmp_path / "tracking.txt"
    malformed.write_text("malformed\n", encoding="utf-8")
    output = tmp_path / "cli-output"
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run_clock_health_check.py"),
            "--mode",
            "files",
            "--policy",
            str(root / "configs" / "clock_health" / "default_policy.json"),
            "--output-dir",
            str(output),
            "--tracking-file",
            str(malformed),
            "--sources-file",
            str(Path(__file__).parent / "fixtures" / "healthy_sources.txt"),
            "--observed-at-utc",
            "2026-08-06T09:00:00Z",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "UNKNOWN"
    assert payload["prediction_lock_allowed"] is False


def test_evidence_bundle_extra_file_is_rejected(
    tmp_path: Path,
    policy,
    tracking_bytes,
    sources_bytes,
) -> None:
    observation = observation_from_bytes(policy, tracking_bytes, sources_bytes)
    decision = evaluate_clock_health(
        observation,
        policy,
        decision_id="extra-file-decision-v1",
        evaluated_at_utc=OBSERVED_AT,
    )
    output = tmp_path / "bundle"
    write_evidence_bundle(
        output,
        observation=observation,
        decision=decision,
        policy=policy,
        tracking_stdout=tracking_bytes,
        sources_stdout=sources_bytes,
    )
    (output / "unexpected.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="missing or extra files"):
        verify_evidence_bundle(output)
