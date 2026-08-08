from __future__ import annotations

from conftest import OBSERVED_AT, observation_from_bytes

from loto.clock_health import ClockHealthStatus, evaluate_clock_health


def _evaluate(policy, tracking: bytes, sources: bytes, **continuity_values):
    observation = observation_from_bytes(
        policy,
        tracking,
        sources,
        **continuity_values,
    )
    return evaluate_clock_health(
        observation,
        policy,
        decision_id="decision-test-v1",
        evaluated_at_utc=OBSERVED_AT,
    )


def test_healthy_fixture_allows_prediction_lock(policy, tracking_bytes, sources_bytes) -> None:
    decision = _evaluate(policy, tracking_bytes, sources_bytes)
    assert decision.status == ClockHealthStatus.HEALTHY
    assert decision.prediction_lock_allowed is True
    assert not decision.failed_checks
    assert not decision.warning_checks
    assert not decision.unknown_checks


def test_warning_threshold_is_degraded(policy, tracking_bytes, sources_bytes) -> None:
    tracking = tracking_bytes.replace(b"+0.000002 seconds", b"+0.010000 seconds")
    decision = _evaluate(policy, tracking, sources_bytes)
    assert decision.status == ClockHealthStatus.DEGRADED
    assert "last-offset" in decision.warning_checks
    assert decision.prediction_lock_allowed is False


def test_unsynchronized_is_blocked(policy, tracking_bytes, sources_bytes) -> None:
    tracking = tracking_bytes.replace(
        b"Leap status     : Normal",
        b"Leap status     : Not synchronised",
    )
    decision = _evaluate(policy, tracking, sources_bytes)
    assert decision.status == ClockHealthStatus.BLOCKED
    assert "synchronized" in decision.failed_checks
    assert "leap-status" in decision.failed_checks


def test_excessive_offset_is_blocked(policy, tracking_bytes, sources_bytes) -> None:
    tracking = tracking_bytes.replace(b"+0.000002 seconds", b"+0.100000 seconds")
    decision = _evaluate(policy, tracking, sources_bytes)
    assert decision.status == ClockHealthStatus.BLOCKED
    assert "last-offset" in decision.failed_checks


def test_excessive_dispersion_is_blocked(policy, tracking_bytes, sources_bytes) -> None:
    tracking = tracking_bytes.replace(b"0.002000 seconds", b"0.200000 seconds")
    decision = _evaluate(policy, tracking, sources_bytes)
    assert decision.status == ClockHealthStatus.BLOCKED
    assert "root-dispersion" in decision.failed_checks


def test_stale_sample_is_blocked(policy, tracking_bytes, sources_bytes) -> None:
    tracking = tracking_bytes.replace(
        b"Thu Aug 06 08:59:30 2026",
        b"Thu Aug 06 08:00:00 2026",
    )
    decision = _evaluate(policy, tracking, sources_bytes)
    assert decision.status == ClockHealthStatus.BLOCKED
    assert "sample-age" in decision.failed_checks


def test_zero_online_source_is_blocked(policy, tracking_bytes) -> None:
    sources = b"MS Name/IP address Stratum Poll Reach LastRx Last sample\n"
    decision = _evaluate(policy, tracking_bytes, sources)
    assert decision.status == ClockHealthStatus.BLOCKED
    assert "online-sources" in decision.failed_checks
    assert "parser" in decision.unknown_checks


def test_malformed_tracking_is_unknown(policy, sources_bytes) -> None:
    decision = _evaluate(policy, b"not chronyc tracking output\n", sources_bytes)
    assert decision.status == ClockHealthStatus.UNKNOWN
    assert "parser" in decision.unknown_checks
    assert decision.prediction_lock_allowed is False


def test_clock_step_is_blocked(policy, tracking_bytes, sources_bytes) -> None:
    decision = _evaluate(
        policy,
        tracking_bytes,
        sources_bytes,
        wall_delta_ns=1_500_000_000,
        monotonic_delta_ns=1_000_000_000,
    )
    assert decision.status == ClockHealthStatus.BLOCKED
    assert decision.clock_step_detected is True
    assert "clock-continuity" in decision.failed_checks
