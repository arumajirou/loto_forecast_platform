from __future__ import annotations

from datetime import datetime, timezone
import pytest

from loto.clock_health import (
    ChronycAdapter,
    ClockContinuityEvidence,
    CommandResult,
    parse_chronyc_observation,
    verify_raw_observation,
)

from conftest import OBSERVED_AT, continuity


class FakeRunner:
    def __init__(self, tracking: bytes, sources: bytes) -> None:
        self.tracking = tracking
        self.sources = sources
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, argv: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        self.calls.append((argv, timeout_seconds))
        stdout = self.tracking if argv[-1] == "tracking" else self.sources
        return CommandResult(
            argv=argv,
            started_at_utc=datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc),
            duration_seconds=0.01,
            exit_code=0,
            timed_out=False,
            stdout=stdout,
            stderr=b"",
        )


def test_chronyc_adapter_uses_fixed_argv(policy, tracking_bytes, sources_bytes) -> None:
    runner = FakeRunner(tracking_bytes, sources_bytes)
    artifacts = ChronycAdapter(runner).observe(
        observation_id="adapter-observation-v1",
        timeout_seconds=3.0,
        continuity_step_threshold_ns=policy.continuity_step_threshold_ns,
    )
    assert runner.calls == [
        (("chronyc", "-n", "tracking"), 3.0),
        (("chronyc", "-n", "sources", "-v"), 3.0),
    ]
    commands = artifacts.observation.parser_evidence.commands
    assert [command.argv for command in commands] == [
        ("chronyc", "-n", "tracking"),
        ("chronyc", "-n", "sources", "-v"),
    ]
    assert all(command.exit_code == 0 for command in commands)


def test_parser_retains_source_identity(policy, tracking_bytes, sources_bytes) -> None:
    observation = parse_chronyc_observation(
        observation_id="parser-observation-v1",
        observed_at_utc=OBSERVED_AT,
        tracking_raw=tracking_bytes,
        sources_raw=sources_bytes,
        continuity=continuity(policy),
    )
    assert observation.synchronized is True
    assert observation.stratum == 2
    assert observation.online_source_count == 2
    assert len(observation.sources) == 2
    assert observation.sources[0].selected is True
    assert observation.parser_evidence.parser_id == "chronyc-text-v1"
    assert len(observation.parser_evidence.parser_code_sha256) == 64


def test_raw_tamper_is_rejected(policy, tracking_bytes, sources_bytes) -> None:
    observation = parse_chronyc_observation(
        observation_id="raw-observation-v1",
        observed_at_utc=OBSERVED_AT,
        tracking_raw=tracking_bytes,
        sources_raw=sources_bytes,
        continuity=continuity(policy),
    )
    with pytest.raises(ValueError, match="tracking raw bytes"):
        verify_raw_observation(
            observation,
            tracking_raw=tracking_bytes + b"tamper",
            sources_raw=sources_bytes,
        )


def test_duplicate_tracking_field_becomes_parser_error(
    policy,
    tracking_bytes,
    sources_bytes,
) -> None:
    observation = parse_chronyc_observation(
        observation_id="duplicate-tracking-v1",
        observed_at_utc=OBSERVED_AT,
        tracking_raw=tracking_bytes + b"Stratum : 3\n",
        sources_raw=sources_bytes,
        continuity=continuity(policy),
    )
    assert any(
        "duplicate tracking field" in error for error in observation.parser_evidence.parse_errors
    )


def test_continuity_hash_rejects_tamper(policy) -> None:
    evidence = continuity(policy)
    with pytest.raises(Exception):
        ClockContinuityEvidence.model_validate(
            {**evidence.model_dump(mode="python"), "wall_delta_ns": 2_000_000_000},
            strict=True,
        )


def test_parser_code_hash_tamper_is_rejected(policy, tracking_bytes, sources_bytes) -> None:
    observation = parse_chronyc_observation(
        observation_id="parser-code-tamper-v1",
        observed_at_utc=OBSERVED_AT,
        tracking_raw=tracking_bytes,
        sources_raw=sources_bytes,
        continuity=continuity(policy),
    )
    tampered_parser = observation.parser_evidence.model_copy(
        update={"parser_code_sha256": "f" * 64}
    )
    tampered = observation.model_copy(update={"parser_evidence": tampered_parser})
    with pytest.raises(ValueError, match="parser code hash"):
        verify_raw_observation(
            tampered,
            tracking_raw=tracking_bytes,
            sources_raw=sources_bytes,
        )
