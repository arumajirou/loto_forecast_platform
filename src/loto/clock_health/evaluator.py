"""Pure fail-closed clock-health policy evaluation."""

from __future__ import annotations

from datetime import datetime

from .contracts import (
    CheckOutcome,
    ClockCheckResult,
    ClockHealthDecision,
    ClockHealthPolicy,
    ClockObservation,
    LeapStatus,
)


def evaluate_clock_health(
    observation: ClockObservation,
    policy: ClockHealthPolicy,
    *,
    decision_id: str,
    evaluated_at_utc: datetime,
) -> ClockHealthDecision:
    checks: list[ClockCheckResult] = []
    checks.append(_check_parser(observation))
    checks.append(_check_synchronized(observation, policy))
    checks.append(_check_leap(observation, policy))
    checks.append(
        _check_threshold(
            "stratum",
            observation.stratum,
            policy.max_stratum_warning,
            policy.max_stratum_block,
        )
    )
    checks.append(
        _check_threshold(
            "last-offset",
            abs(observation.last_offset_seconds)
            if observation.last_offset_seconds is not None
            else None,
            policy.max_abs_last_offset_warning_seconds,
            policy.max_abs_last_offset_block_seconds,
        )
    )
    checks.append(
        _check_threshold(
            "rms-offset",
            observation.rms_offset_seconds,
            policy.max_rms_offset_warning_seconds,
            policy.max_rms_offset_block_seconds,
        )
    )
    checks.append(
        _check_threshold(
            "root-delay",
            observation.root_delay_seconds,
            policy.max_root_delay_warning_seconds,
            policy.max_root_delay_block_seconds,
        )
    )
    checks.append(
        _check_threshold(
            "root-dispersion",
            observation.root_dispersion_seconds,
            policy.max_root_dispersion_warning_seconds,
            policy.max_root_dispersion_block_seconds,
        )
    )
    checks.append(
        _check_threshold(
            "skew-ppm",
            observation.skew_ppm,
            policy.max_skew_warning_ppm,
            policy.max_skew_block_ppm,
        )
    )
    checks.append(_check_sources(observation, policy))
    checks.append(
        _check_threshold(
            "sample-age",
            observation.sample_age_seconds,
            policy.max_sample_age_warning_seconds,
            policy.max_sample_age_block_seconds,
        )
    )
    checks.append(_check_continuity(observation, policy))
    continuity = observation.continuity
    return ClockHealthDecision.create(
        decision_id=decision_id,
        observation_sha256=observation.observation_sha256,
        policy_sha256=policy.policy_sha256,
        checks=tuple(checks),
        clock_step_detected=bool(continuity and continuity.clock_step_detected),
        evaluated_at_utc=evaluated_at_utc,
    )


def _check_parser(observation: ClockObservation) -> ClockCheckResult:
    evidence = observation.parser_evidence
    command_failures = [
        command for command in evidence.commands if command.timed_out or command.exit_code != 0
    ]
    if evidence.parse_errors or command_failures:
        return _result(
            "parser",
            CheckOutcome.UNKNOWN,
            f"parse_errors={len(evidence.parse_errors)},command_failures={len(command_failures)}",
            "zero",
            "parser-evidence-incomplete",
        )
    return _result("parser", CheckOutcome.PASS, "complete", "complete", "parser-complete")


def _check_synchronized(
    observation: ClockObservation,
    policy: ClockHealthPolicy,
) -> ClockCheckResult:
    if observation.synchronized is None:
        return _result(
            "synchronized",
            CheckOutcome.UNKNOWN,
            "unknown",
            str(policy.require_synchronized).lower(),
            "synchronization-unknown",
        )
    if policy.require_synchronized and not observation.synchronized:
        return _result(
            "synchronized",
            CheckOutcome.FAIL,
            "false",
            "true",
            "clock-unsynchronized",
        )
    return _result(
        "synchronized",
        CheckOutcome.PASS,
        str(observation.synchronized).lower(),
        str(policy.require_synchronized).lower(),
        "synchronization-acceptable",
    )


def _check_leap(
    observation: ClockObservation,
    policy: ClockHealthPolicy,
) -> ClockCheckResult:
    status = observation.leap_status
    if status == LeapStatus.UNKNOWN:
        return _result("leap-status", CheckOutcome.UNKNOWN, status.value, "known", "leap-unknown")
    if status == LeapStatus.NOT_SYNCHRONIZED:
        return _result(
            "leap-status",
            CheckOutcome.FAIL,
            status.value,
            "synchronized",
            "leap-not-synchronized",
        )
    if status in policy.allowed_leap_statuses:
        return _result("leap-status", CheckOutcome.PASS, status.value, "allowed", "leap-allowed")
    if status in policy.warning_leap_statuses:
        return _result(
            "leap-status",
            CheckOutcome.WARNING,
            status.value,
            "normal-preferred",
            "leap-warning",
        )
    return _result("leap-status", CheckOutcome.FAIL, status.value, "allowed", "leap-forbidden")


def _check_threshold(
    check_id: str,
    observed: float | int | None,
    warning: float | int,
    blocked: float | int,
) -> ClockCheckResult:
    if observed is None:
        return _result(
            check_id,
            CheckOutcome.UNKNOWN,
            "unknown",
            f"warning<={warning},block>{blocked}",
            f"{check_id}-unknown",
        )
    if observed > blocked:
        return _result(
            check_id,
            CheckOutcome.FAIL,
            _format_number(observed),
            f"<={blocked}",
            f"{check_id}-blocked",
        )
    if observed > warning:
        return _result(
            check_id,
            CheckOutcome.WARNING,
            _format_number(observed),
            f"<={warning}",
            f"{check_id}-warning",
        )
    return _result(
        check_id,
        CheckOutcome.PASS,
        _format_number(observed),
        f"<={warning}",
        f"{check_id}-acceptable",
    )


def _check_sources(
    observation: ClockObservation,
    policy: ClockHealthPolicy,
) -> ClockCheckResult:
    count = observation.online_source_count
    if count is None:
        return _result(
            "online-sources",
            CheckOutcome.UNKNOWN,
            "unknown",
            f">={policy.min_online_sources_healthy}",
            "source-count-unknown",
        )
    if count == 0:
        return _result(
            "online-sources",
            CheckOutcome.FAIL,
            "0",
            f">={policy.min_online_sources_healthy}",
            "zero-online-sources",
        )
    if count < policy.min_online_sources_healthy:
        return _result(
            "online-sources",
            CheckOutcome.WARNING,
            str(count),
            f">={policy.min_online_sources_healthy}",
            "insufficient-source-redundancy",
        )
    return _result(
        "online-sources",
        CheckOutcome.PASS,
        str(count),
        f">={policy.min_online_sources_healthy}",
        "source-count-acceptable",
    )


def _check_continuity(
    observation: ClockObservation,
    policy: ClockHealthPolicy,
) -> ClockCheckResult:
    continuity = observation.continuity
    if continuity is None:
        outcome = CheckOutcome.UNKNOWN if policy.require_continuity else CheckOutcome.PASS
        return _result(
            "clock-continuity",
            outcome,
            "missing",
            str(policy.require_continuity).lower(),
            "continuity-missing" if policy.require_continuity else "continuity-not-required",
        )
    if continuity.step_threshold_ns != policy.continuity_step_threshold_ns:
        return _result(
            "clock-continuity",
            CheckOutcome.UNKNOWN,
            str(continuity.step_threshold_ns),
            str(policy.continuity_step_threshold_ns),
            "continuity-policy-mismatch",
        )
    if continuity.clock_step_detected:
        return _result(
            "clock-continuity",
            CheckOutcome.FAIL,
            str(continuity.difference_ns),
            f"<={policy.continuity_step_threshold_ns}",
            "clock-step-detected",
        )
    return _result(
        "clock-continuity",
        CheckOutcome.PASS,
        str(continuity.difference_ns),
        f"<={policy.continuity_step_threshold_ns}",
        "clock-continuity-stable",
    )


def _result(
    check_id: str,
    outcome: CheckOutcome,
    observed: str,
    policy: str,
    reason: str,
) -> ClockCheckResult:
    return ClockCheckResult(
        check_id=check_id,
        outcome=outcome,
        observed_value=observed,
        policy_value=policy,
        reason_code=reason,
    )


def _format_number(value: float | int) -> str:
    return format(value, ".12g")
