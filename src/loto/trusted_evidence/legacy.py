"""Compatibility adapters for existing prediction and actual lock schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .contracts import (
    ActualSourceEvidence,
    ParserEvidence,
    ThirdPartyEvidenceBundle,
    TrustedTimeEvidence,
)
from .statuses import EvidenceStatus, TimestampAuthority


def legacy_prediction_time_evidence(
    prediction_lock: dict[str, Any],
    *,
    prediction_lock_sha256: str,
) -> TrustedTimeEvidence:
    authority = str(prediction_lock.get("timestamp_authority") or "")
    locked_at = prediction_lock.get("locked_at")
    if authority == "LOCAL_SYSTEM_UTC" and locked_at:
        parsed = datetime.fromisoformat(str(locked_at).replace("Z", "+00:00"))
        return TrustedTimeEvidence(
            evidence_id="legacy-prediction-lock-local-time",
            status=EvidenceStatus.LOCALLY_TIMESTAMPED,
            subject_sha256=prediction_lock_sha256,
            claimed_time_utc=parsed,
            recorded_at_utc=parsed,
            authority=TimestampAuthority.LOCAL_SYSTEM,
            verification_materials=[],
            verification_material_sha256=None,
        )
    return TrustedTimeEvidence(
        evidence_id="legacy-prediction-lock-time-not-provided",
        status=EvidenceStatus.NOT_PROVIDED,
        subject_sha256=prediction_lock_sha256,
        claimed_time_utc=None,
        recorded_at_utc=None,
        authority=TimestampAuthority.NONE,
        verification_materials=[],
        verification_material_sha256=None,
    )


def legacy_actual_source_evidence(
    actuals_lock: dict[str, Any] | None,
    *,
    actuals_lock_sha256: str | None,
) -> ActualSourceEvidence | None:
    if actuals_lock is None or actuals_lock_sha256 is None:
        return None
    parser = ParserEvidence(
        evidence_id="legacy-actual-parser-assertion",
        status=EvidenceStatus.OPERATOR_ASSERTED,
        parser_name="legacy-actual-lock-parser",
        parser_version=str(actuals_lock.get("schema_version") or "UNKNOWN"),
        parser_code_sha256=actuals_lock_sha256,
        source_format="LEGACY_ACTUALS_LOCK",
        input_raw_bytes_sha256=str(
            (actuals_lock.get("actuals_input") or {}).get("sha256")
        ),
        output_payload_sha256=str(actuals_lock.get("actuals_normalized_sha256")),
        parsed_at_utc=datetime.fromisoformat(
            str(actuals_lock.get("ingested_at")).replace("Z", "+00:00")
        ),
    )
    return ActualSourceEvidence(
        evidence_id="legacy-actual-source-assertion",
        status=EvidenceStatus.OPERATOR_ASSERTED,
        source_name=str(actuals_lock.get("actual_source_label") or "UNSPECIFIED"),
        source_url=None,
        raw_bytes_sha256=str((actuals_lock.get("actuals_input") or {}).get("sha256")),
        raw_bytes_size=0,
        headers_sha256=None,
        fetched_at_utc=datetime.fromisoformat(
            str(actuals_lock.get("ingested_at")).replace("Z", "+00:00")
        ),
        published_at_utc=(
            datetime.fromisoformat(
                str(actuals_lock.get("actual_published_at")).replace("Z", "+00:00")
            )
            if actuals_lock.get("actual_published_at")
            else None
        ),
        normalized_actuals_sha256=str(actuals_lock.get("actuals_normalized_sha256")),
        parser=parser,
        source_revision=None,
        publication_time_evidence=None,
        signature=None,
        verifier_id=None,
        correction_head_sha256=None,
        verification_materials=[],
        verification_material_sha256=None,
    )


def legacy_bundle(
    *,
    bundle_id: str,
    prediction_lock: dict[str, Any],
    prediction_lock_sha256: str,
    verification_seal_sha256: str,
    actuals_lock: dict[str, Any] | None,
    actuals_lock_sha256: str | None,
    created_at_utc: datetime,
) -> ThirdPartyEvidenceBundle:
    return ThirdPartyEvidenceBundle.create(
        bundle_id=bundle_id,
        prediction_lock_sha256=prediction_lock_sha256,
        verification_seal_sha256=verification_seal_sha256,
        actuals_lock_sha256=actuals_lock_sha256,
        created_at_utc=created_at_utc,
        trusted_time=[
            legacy_prediction_time_evidence(
                prediction_lock,
                prediction_lock_sha256=prediction_lock_sha256,
            )
        ],
        signatures=[],
        actual_source=legacy_actual_source_evidence(
            actuals_lock,
            actuals_lock_sha256=actuals_lock_sha256,
        ),
        corrections=[],
    )
