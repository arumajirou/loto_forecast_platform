from __future__ import annotations

from typing import Any

from loto.orchestration.pipeline_downstream_preflight_errors import (
    DownstreamCommitPreflightError,
)
from loto.orchestration.pipeline_downstream_types import canonical_json_bytes


def default_ledger_validator(
    ledger_payload: dict[str, Any],
    saved_validation: dict[str, Any],
) -> dict[str, Any]:
    from loto.data_access_ledger import (
        AccessDecision,
        DataAccessLedger,
        validate_ledger,
    )

    ledger = DataAccessLedger.model_validate(ledger_payload)
    fresh = validate_ledger(ledger)
    fresh_payload = fresh.model_dump(mode="json")
    if fresh.status is not AccessDecision.PASS:
        codes = [item.code.value for item in fresh.findings]
        raise DownstreamCommitPreflightError(
            "fresh Data Access Ledger validation did not PASS: " + ",".join(codes)
        )
    if canonical_json_bytes(fresh_payload) != canonical_json_bytes(saved_validation):
        raise DownstreamCommitPreflightError(
            "saved Data Access Ledger validation does not match fresh validation"
        )
    return {
        "run_id": ledger.run_id,
        "ledger_sha256": ledger.ledger_sha256,
        "verified_events": fresh.verified_event_count,
    }


def default_seal_verifier(sealed: dict[str, Any], secret: bytes) -> bool:
    from loto.sealing.manifest import verify_seal

    return bool(verify_seal(sealed, secret))


def float_metrics(
    evaluation: dict[str, Any],
    champion: str,
) -> dict[str, float]:
    selected = evaluation.get(champion)
    if not isinstance(selected, dict):
        raise DownstreamCommitPreflightError(
            f"evaluation does not contain champion metrics: {champion}"
        )
    metrics: dict[str, float] = {}
    for key, value in selected.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        metrics[f"{champion}_{key}"] = float(value)
    if not metrics:
        raise DownstreamCommitPreflightError("champion evaluation contains no numeric metrics")
    return metrics
