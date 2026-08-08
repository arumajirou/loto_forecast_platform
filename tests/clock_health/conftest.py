from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from loto.clock_health import (
    ClockContinuityEvidence,
    ClockHealthPolicy,
    ClockObservation,
    parse_chronyc_observation,
)

FIXTURES = Path(__file__).parent / "fixtures"
OBSERVED_AT = datetime(2026, 8, 6, 9, 0, 0, tzinfo=UTC)


@pytest.fixture
def policy() -> ClockHealthPolicy:
    return ClockHealthPolicy.create(policy_id="test-policy-v1")


@pytest.fixture
def tracking_bytes() -> bytes:
    return (FIXTURES / "healthy_tracking.txt").read_bytes()


@pytest.fixture
def sources_bytes() -> bytes:
    return (FIXTURES / "healthy_sources.txt").read_bytes()


def continuity(
    policy: ClockHealthPolicy,
    *,
    wall_delta_ns: int = 1_000_000_000,
    monotonic_delta_ns: int = 1_000_000_000,
) -> ClockContinuityEvidence:
    return ClockContinuityEvidence.create(
        sample_id="continuity-test-v1",
        started_at_utc=OBSERVED_AT - timedelta(seconds=1),
        ended_at_utc=OBSERVED_AT,
        wall_delta_ns=wall_delta_ns,
        monotonic_delta_ns=monotonic_delta_ns,
        step_threshold_ns=policy.continuity_step_threshold_ns,
    )


def observation_from_bytes(
    policy: ClockHealthPolicy,
    tracking: bytes,
    sources: bytes,
    *,
    wall_delta_ns: int = 1_000_000_000,
    monotonic_delta_ns: int = 1_000_000_000,
) -> ClockObservation:
    return parse_chronyc_observation(
        observation_id="observation-test-v1",
        observed_at_utc=OBSERVED_AT,
        tracking_raw=tracking,
        sources_raw=sources,
        continuity=continuity(
            policy,
            wall_delta_ns=wall_delta_ns,
            monotonic_delta_ns=monotonic_delta_ns,
        ),
    )
