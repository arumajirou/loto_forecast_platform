from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from loto.sktime_campaign.approval_authorization import (
    ApprovalAuthorizationRequest,
    AuthorizationConsumptionLedger,
    HumanApproval,
    RegistryTransactionRequest,
    approval_intent_payload,
    approval_signing_payload,
    canonical_sha256,
    issue_registry_authorization,
    validate_registry_transaction_request,
    verify_registry_authorization,
)

HASH = "a" * 64
OTHER_HASH = "b" * 64
REQUESTED = "2026-08-05T09:00:00Z"
APPROVED_1 = "2026-08-05T09:05:00Z"
APPROVED_2 = "2026-08-05T09:06:00Z"
ISSUED = "2026-08-05T09:10:00Z"
EXPIRES = "2026-08-05T10:00:00Z"
RISKS = [
    "REAL_PROSPECTIVE_ACCURACY_REVIEWED",
    "BASELINE_COMPARISON_REVIEWED",
    "LEAKAGE_AND_INTEGRITY_REVIEWED",
    "ROLLBACK_PLAN_REVIEWED",
]


def verifier(approval: HumanApproval, payload: bytes) -> bool:
    return approval.signature.startswith("VALID-") and bool(payload)


def _approval(
    *,
    role: str,
    approver_id: str,
    signer_identity: str,
    approved_at: str,
    intent_sha256: str,
    risks: list[str] | None = None,
    signature: str = "VALID-SSH-SIGNATURE-BLOCK-1234567890",
) -> HumanApproval:
    provisional = HumanApproval(
        role=role,
        approver_id=approver_id,
        signer_identity=signer_identity,
        approved_at_utc=approved_at,
        approval_intent_sha256=intent_sha256,
        signed_payload_sha256="0" * 64,
        signature=signature,
        risk_acknowledgements=risks or RISKS,
        rationale="Reviewed evidence, risks, rollback, and exact registry subject.",
    )
    payload_sha256 = canonical_sha256(approval_signing_payload(provisional))
    return provisional.model_copy(update={"signed_payload_sha256": payload_sha256})


def make_request(**updates: object) -> ApprovalAuthorizationRequest:
    base = {
        "output_dir": "/tmp/p7-output",
        "run_id": "p7-test",
        "git_commit": "1" * 40,
        "code_sha256": HASH,
        "config_sha256": HASH,
        "allowed_signers_sha256": HASH,
        "approval_requested_at_utc": REQUESTED,
        "authorization_expires_at_utc": EXPIRES,
        "authorization_nonce": "c" * 64,
        "p6": {
            "p6_bundle_sha256": HASH,
            "p6_decision_sha256": OTHER_HASH,
            "p6_run_id": "p6-test",
            "shadow_candidate_id": "theta",
            "decision": "ELIGIBLE_FOR_HUMAN_APPROVAL",
        },
        "subject": {
            "registry_target": "mlflow://models/sktime-champion",
            "model_id": "sktime-theta",
            "model_revision": "1" * 40,
            "shadow_candidate_id": "theta",
            "model_artifact_sha256": HASH,
            "data_snapshot_sha256": OTHER_HASH,
            "runtime_environment_sha256": "c" * 64,
            "code_sha256": "d" * 64,
        },
        "policy": {},
        "approvals": [
            {
                "role": "model_owner",
                "approver_id": "owner@example",
                "signer_identity": "owner@example",
                "approved_at_utc": APPROVED_1,
                "approval_intent_sha256": "0" * 64,
                "signed_payload_sha256": "0" * 64,
                "signature": "VALID-SSH-SIGNATURE-BLOCK-1234567890",
                "risk_acknowledgements": RISKS,
                "rationale": ("Reviewed evidence, risks, rollback, and exact subject."),
            },
            {
                "role": "independent_reviewer",
                "approver_id": "reviewer@example",
                "signer_identity": "reviewer@example",
                "approved_at_utc": APPROVED_2,
                "approval_intent_sha256": "0" * 64,
                "signed_payload_sha256": "0" * 64,
                "signature": "VALID-SSH-SIGNATURE-BLOCK-0987654321",
                "risk_acknowledgements": RISKS,
                "rationale": ("Independently reviewed metrics, integrity, and rollback."),
            },
        ],
    }
    base.update(updates)
    provisional = ApprovalAuthorizationRequest.model_validate(base)
    intent_sha256 = canonical_sha256(approval_intent_payload(provisional))
    approvals = [
        _approval(
            role="model_owner",
            approver_id="owner@example",
            signer_identity="owner@example",
            approved_at=APPROVED_1,
            intent_sha256=intent_sha256,
        ),
        _approval(
            role="independent_reviewer",
            approver_id="reviewer@example",
            signer_identity="reviewer@example",
            approved_at=APPROVED_2,
            intent_sha256=intent_sha256,
            signature="VALID-SSH-SIGNATURE-BLOCK-0987654321",
        ),
    ]
    if "approvals" not in updates:
        provisional = provisional.model_copy(update={"approvals": approvals})
    return provisional


def test_issue_registry_authorization_passes() -> None:
    result = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )
    assert result["status"] == "PASS"
    assert result["registry_write_authorized"] is True
    assert result["registry_write_executed"] is False
    assert result["promotion_status"] == "APPROVED_NOT_REGISTERED"
    assert len(result["signature_verification"]) == 2


def test_distinct_approvers_are_required() -> None:
    request = make_request()
    approvals = [
        request.approvals[0],
        request.approvals[1].model_copy(update={"approver_id": request.approvals[0].approver_id}),
    ]
    with pytest.raises(ValidationError, match="approvers must be distinct"):
        ApprovalAuthorizationRequest.model_validate(
            {**request.model_dump(), "approvals": approvals}
        )


def test_distinct_signers_are_required() -> None:
    request = make_request()
    approvals = [
        request.approvals[0],
        request.approvals[1].model_copy(
            update={"signer_identity": request.approvals[0].signer_identity}
        ),
    ]
    with pytest.raises(ValidationError, match="signers must be distinct"):
        ApprovalAuthorizationRequest.model_validate(
            {**request.model_dump(), "approvals": approvals}
        )


def test_exact_role_inventory_is_required() -> None:
    request = make_request()
    approvals = [request.approvals[0], request.approvals[0].model_copy()]
    with pytest.raises(ValidationError, match="approval role inventory"):
        ApprovalAuthorizationRequest.model_validate(
            {**request.model_dump(), "approvals": approvals}
        )


def test_subject_cannot_change_shadow_candidate() -> None:
    request = make_request()
    subject = request.subject.model_copy(update={"shadow_candidate_id": "other"})
    with pytest.raises(ValidationError, match="changed P6 shadow candidate"):
        ApprovalAuthorizationRequest.model_validate({**request.model_dump(), "subject": subject})


def test_authorization_lifetime_cannot_exceed_policy() -> None:
    with pytest.raises(ValidationError, match="lifetime exceeds policy"):
        make_request(authorization_expires_at_utc="2026-08-05T11:00:01Z")


def test_approval_timestamp_must_be_inside_window() -> None:
    request = make_request()
    approvals = [
        request.approvals[0].model_copy(update={"approved_at_utc": "2026-08-05T08:59:59Z"}),
        request.approvals[1],
    ]
    with pytest.raises(ValidationError, match="outside ceremony window"):
        ApprovalAuthorizationRequest.model_validate(
            {**request.model_dump(), "approvals": approvals}
        )


def test_approval_intent_mismatch_fails_closed() -> None:
    request = make_request()
    approvals = [
        request.approvals[0].model_copy(update={"approval_intent_sha256": OTHER_HASH}),
        request.approvals[1],
    ]
    request = request.model_copy(update={"approvals": approvals})
    with pytest.raises(ValueError, match="different intent"):
        issue_registry_authorization(
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_risk_acknowledgement_mismatch_fails_closed() -> None:
    request = make_request()
    approvals = [
        request.approvals[0].model_copy(update={"risk_acknowledgements": RISKS[:-1] + ["OTHER"]}),
        request.approvals[1],
    ]
    request = request.model_copy(update={"approvals": approvals})
    with pytest.raises(ValueError, match="risk acknowledgement mismatch"):
        issue_registry_authorization(
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_signed_payload_hash_mismatch_fails_closed() -> None:
    request = make_request()
    approvals = [
        request.approvals[0].model_copy(update={"signed_payload_sha256": OTHER_HASH}),
        request.approvals[1],
    ]
    request = request.model_copy(update={"approvals": approvals})
    with pytest.raises(ValueError, match="signed approval payload"):
        issue_registry_authorization(
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_invalid_signature_fails_closed() -> None:
    request = make_request()
    approvals = [
        request.approvals[0].model_copy(
            update={"signature": "INVALID-SIGNATURE-BLOCK-123456789012345"}
        ),
        request.approvals[1],
    ]
    request = request.model_copy(update={"approvals": approvals})
    with pytest.raises(ValueError, match="signature verification failed"):
        issue_registry_authorization(
            request,
            issued_at_utc=ISSUED,
            signature_verifier=verifier,
        )


def test_expired_ceremony_fails_closed() -> None:
    with pytest.raises(ValueError, match="has expired"):
        issue_registry_authorization(
            make_request(),
            issued_at_utc="2026-08-05T10:00:01Z",
            signature_verifier=verifier,
        )


def test_verification_before_request_fails_closed() -> None:
    with pytest.raises(ValueError, match="precedes approval request"):
        issue_registry_authorization(
            make_request(),
            issued_at_utc="2026-08-05T08:59:59Z",
            signature_verifier=verifier,
        )


def test_authorization_seal_detects_tampering() -> None:
    authorization = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )["authorization"]
    tampered = deepcopy(authorization)
    tampered["subject"]["model_id"] = "tampered"
    with pytest.raises(ValueError, match="seal mismatch"):
        verify_registry_authorization(tampered)


def test_automatic_promotion_cannot_be_enabled() -> None:
    authorization = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )["authorization"]
    tampered = deepcopy(authorization)
    tampered["automatic_promotion"] = True
    payload = {key: value for key, value in tampered.items() if key != "seal_sha256"}
    tampered["seal_sha256"] = canonical_sha256(payload)
    with pytest.raises(ValueError, match="automatic promotion"):
        verify_registry_authorization(tampered)


def _transaction(
    authorization: dict[str, object],
) -> RegistryTransactionRequest:
    return RegistryTransactionRequest(
        authorization_id=authorization["authorization_id"],
        authorization_seal_sha256=authorization["seal_sha256"],
        transaction_nonce="e" * 64,
        requested_at_utc="2026-08-05T09:15:00Z",
        expected_registry_state_sha256="f" * 64,
        subject=authorization["subject"],
    )


def test_exact_transaction_is_allowed_once() -> None:
    authorization = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )["authorization"]
    result = validate_registry_transaction_request(
        authorization,
        _transaction(authorization),
        AuthorizationConsumptionLedger(),
        verified_at_utc="2026-08-05T09:16:00Z",
    )
    assert result["decision"] == "REGISTRY_TRANSACTION_ALLOWED_ONCE"
    assert result["registry_write_executed"] is False


def test_transaction_authorization_id_must_match() -> None:
    authorization = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )["authorization"]
    transaction = _transaction(authorization).model_copy(update={"authorization_id": OTHER_HASH})
    with pytest.raises(ValueError, match="authorization ID mismatch"):
        validate_registry_transaction_request(
            authorization,
            transaction,
            AuthorizationConsumptionLedger(),
            verified_at_utc="2026-08-05T09:16:00Z",
        )


def test_transaction_subject_must_match_exactly() -> None:
    authorization = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )["authorization"]
    transaction = _transaction(authorization)
    subject = transaction.subject.model_copy(update={"model_id": "other"})
    transaction = transaction.model_copy(update={"subject": subject})
    with pytest.raises(ValueError, match="subject differs"):
        validate_registry_transaction_request(
            authorization,
            transaction,
            AuthorizationConsumptionLedger(),
            verified_at_utc="2026-08-05T09:16:00Z",
        )


def test_consumed_authorization_is_rejected() -> None:
    authorization = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )["authorization"]
    ledger = AuthorizationConsumptionLedger(
        consumed_authorization_ids=[authorization["authorization_id"]]
    )
    with pytest.raises(ValueError, match="already consumed"):
        validate_registry_transaction_request(
            authorization,
            _transaction(authorization),
            ledger,
            verified_at_utc="2026-08-05T09:16:00Z",
        )


def test_consumed_transaction_nonce_is_rejected() -> None:
    authorization = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )["authorization"]
    transaction = _transaction(authorization)
    ledger = AuthorizationConsumptionLedger(
        consumed_transaction_nonces=[transaction.transaction_nonce]
    )
    with pytest.raises(ValueError, match="nonce was already consumed"):
        validate_registry_transaction_request(
            authorization,
            transaction,
            ledger,
            verified_at_utc="2026-08-05T09:16:00Z",
        )


def test_transaction_after_expiry_is_rejected() -> None:
    authorization = issue_registry_authorization(
        make_request(),
        issued_at_utc=ISSUED,
        signature_verifier=verifier,
    )["authorization"]
    with pytest.raises(ValueError, match="outside authorization window"):
        validate_registry_transaction_request(
            authorization,
            _transaction(authorization),
            AuthorizationConsumptionLedger(),
            verified_at_utc="2026-08-05T10:00:01Z",
        )


def test_duplicate_ledger_entries_are_rejected() -> None:
    with pytest.raises(ValidationError, match="authorization IDs must be unique"):
        AuthorizationConsumptionLedger(consumed_authorization_ids=[HASH, HASH])
