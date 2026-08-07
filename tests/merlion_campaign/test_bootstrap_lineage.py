from __future__ import annotations

from copy import deepcopy

import pytest

from loto.merlion_campaign.bootstrap_lineage import (
    validate_preflight_payload,
    validate_preflight_plan_lineage,
)
from loto.merlion_campaign.bootstrap_resume import _canonical_sha256


def _preflight() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "merlion-bootstrap-preflight-v1",
        "status": "READY",
        "can_attempt_bootstrap": True,
    }
    payload["report_sha256"] = _canonical_sha256(payload)
    return payload


def _plan(preflight: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "merlion-bootstrap-resume-plan-v1",
        "status": "READY_TO_BOOTSTRAP",
        "preflight_report_sha256": preflight["report_sha256"],
    }
    payload["plan_sha256"] = _canonical_sha256(payload)
    return payload


def test_preflight_plan_lineage_passes() -> None:
    preflight = _preflight()
    lineage = validate_preflight_plan_lineage(
        preflight,
        _plan(preflight),
        require_attemptable=True,
    )
    assert lineage["preflight_report_sha256"] == preflight["report_sha256"]


def test_preflight_expected_hash_mismatch_is_blocked() -> None:
    preflight = _preflight()
    with pytest.raises(ValueError, match="expected lineage"):
        validate_preflight_payload(
            preflight,
            require_attemptable=True,
            expected_report_sha256="0" * 64,
        )


def test_mutated_preflight_is_blocked() -> None:
    preflight = _preflight()
    mutated = deepcopy(preflight)
    mutated["status"] = "BLOCKED"
    with pytest.raises(ValueError, match="report_sha256 mismatch"):
        validate_preflight_plan_lineage(
            mutated,
            _plan(preflight),
            require_attemptable=True,
        )


def test_plan_bound_to_another_preflight_is_blocked() -> None:
    preflight = _preflight()
    plan = _plan(preflight)
    plan["preflight_report_sha256"] = "f" * 64
    plan["plan_sha256"] = _canonical_sha256(plan, omit="plan_sha256")
    with pytest.raises(ValueError, match="preflight hash mismatch"):
        validate_preflight_plan_lineage(
            preflight,
            plan,
            require_attemptable=True,
        )
