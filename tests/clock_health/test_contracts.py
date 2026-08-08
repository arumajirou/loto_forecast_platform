from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from loto.clock_health import (
    CanonicalizationError,
    ClockHealthDecision,
    ClockHealthPolicy,
    ClockHealthStatus,
    loads_strict_object,
)


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ClockHealthPolicy.model_validate(
            {
                "schema_version": "1.0.0",
                "policy_id": "p1",
                "policy_sha256": "0" * 64,
                "unexpected": True,
            },
            strict=True,
        )


def test_duplicate_json_key_is_rejected() -> None:
    with pytest.raises(CanonicalizationError, match="duplicate JSON key"):
        loads_strict_object('{"policy_id":"a","policy_id":"b"}')


def test_policy_hash_changes_with_threshold(policy: ClockHealthPolicy) -> None:
    changed = ClockHealthPolicy.create(
        policy_id=policy.policy_id,
        max_abs_last_offset_warning_seconds=0.004,
    )
    assert changed.policy_sha256 != policy.policy_sha256


def test_policy_hash_tamper_is_rejected(policy: ClockHealthPolicy) -> None:
    with pytest.raises(ValidationError, match="policy_sha256 mismatch"):
        ClockHealthPolicy.model_validate(
            {**policy.model_dump(mode="python"), "policy_sha256": "f" * 64},
            strict=True,
        )


def test_local_health_cannot_generate_trusted_evidence(
    healthy_decision: ClockHealthDecision,
) -> None:
    assert healthy_decision.status == ClockHealthStatus.HEALTHY
    assert healthy_decision.prediction_lock_allowed is True
    assert healthy_decision.external_trust_established is False
    assert healthy_decision.trusted_time_evidence_generated is False
    assert healthy_decision.signature_evidence_generated is False
    with pytest.raises(ValidationError):
        ClockHealthDecision.model_validate(
            {
                **healthy_decision.model_dump(mode="python"),
                "external_trust_established": True,
            },
            strict=True,
        )


@pytest.fixture
def healthy_decision(policy, tracking_bytes, sources_bytes):
    from loto.clock_health import evaluate_clock_health
    from tests.clock_health.conftest import observation_from_bytes

    observation = observation_from_bytes(policy, tracking_bytes, sources_bytes)
    return evaluate_clock_health(
        observation,
        policy,
        decision_id="healthy-decision-v1",
        evaluated_at_utc=datetime(2026, 8, 6, 9, 0, tzinfo=UTC),
    )


def test_policy_create_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown policy fields"):
        ClockHealthPolicy.create(policy_id="p1", unexpected=True)


def test_strict_integer_rejects_boolean(policy: ClockHealthPolicy) -> None:
    payload = policy.model_dump(mode="python")
    payload["max_stratum_warning"] = True
    with pytest.raises(ValidationError):
        ClockHealthPolicy.model_validate(payload, strict=True)
