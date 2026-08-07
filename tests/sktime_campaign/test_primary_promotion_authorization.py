from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.sktime_campaign.primary_promotion_authorization import (
    PrimaryPromotionAuthorizationRequest,
    PrimaryPromotionTransactionRequest,
    canonical_sha256,
    issue_primary_promotion_authorization,
    validate_primary_promotion_transaction,
    verify_authorization_seal,
)
from p11_helpers import (
    build_request,
    failing_verifier,
    fake_verifier,
)


def issue(tmp_path: Path):
    request = build_request(tmp_path)
    result = issue_primary_promotion_authorization(
        request,
        issued_at_utc="2026-08-05T10:25:00Z",
        signature_verifier=fake_verifier,
    )
    return request, result["authorization"]


def transaction_from(authorization: dict) -> PrimaryPromotionTransactionRequest:
    return PrimaryPromotionTransactionRequest(
        authorization_id=authorization["authorization_id"],
        authorization_seal_sha256=authorization["seal_sha256"],
        transaction_nonce="d4" * 32,
        requested_at_utc="2026-08-05T10:26:00Z",
        deployment_target=authorization["deployment_target"],
        expected_deployment_state_sha256=(
            authorization["expected_deployment_state_sha256"]
        ),
        expected_primary_before=authorization["expected_primary_before"],
        expected_canary_before=authorization["expected_canary_before"],
        target_primary=authorization["target_primary"],
        clear_canary_on_commit=True,
    )


def test_issue_success(tmp_path):
    request, authorization = issue(tmp_path)
    assert authorization["decision"] == (
        "AUTHORIZED_FOR_ONE_PRIMARY_PROMOTION_TRANSACTION"
    )
    assert authorization["primary_promotion_authorized"] is True
    assert authorization["primary_promotion_executed"] is False
    assert authorization["target_primary"]["mode"] == "primary"
    assert authorization["expected_canary_before"]["mode"] == "shadow_canary"
    assert authorization["rollback_target"] == (
        request.deployment.primary_binding.model_dump(mode="json")
    )
    verify_authorization_seal(authorization)


def test_signature_failure_rejected(tmp_path):
    request = build_request(tmp_path)
    with pytest.raises(ValueError, match="signature verification failed"):
        issue_primary_promotion_authorization(
            request,
            issued_at_utc="2026-08-05T10:25:00Z",
            signature_verifier=failing_verifier,
        )


def test_issue_after_expiry_rejected(tmp_path):
    request = build_request(tmp_path)
    with pytest.raises(ValueError, match="outside the valid window"):
        issue_primary_promotion_authorization(
            request,
            issued_at_utc="2026-08-05T10:41:00Z",
            signature_verifier=fake_verifier,
        )


def test_allowed_signers_tamper_rejected(tmp_path):
    request = build_request(tmp_path)
    Path(request.allowed_signers_file).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="allowed signers SHA mismatch"):
        issue_primary_promotion_authorization(
            request,
            issued_at_utc="2026-08-05T10:25:00Z",
            signature_verifier=fake_verifier,
        )


def test_duplicate_approvers_rejected(tmp_path):
    request = build_request(tmp_path)
    payload = request.model_dump(mode="json")
    payload["approvals"][1]["approver_id"] = payload["approvals"][0]["approver_id"]
    with pytest.raises(ValidationError, match="approver IDs must be distinct"):
        PrimaryPromotionAuthorizationRequest.model_validate(payload)


def test_duplicate_signers_rejected(tmp_path):
    request = build_request(tmp_path)
    payload = request.model_dump(mode="json")
    payload["approvals"][1]["signer_identity"] = (
        payload["approvals"][0]["signer_identity"]
    )
    with pytest.raises(ValidationError, match="signer identities must be distinct"):
        PrimaryPromotionAuthorizationRequest.model_validate(payload)


def test_missing_role_rejected(tmp_path):
    request = build_request(tmp_path)
    payload = request.model_dump(mode="json")
    payload["approvals"] = payload["approvals"][:2]
    with pytest.raises(ValidationError, match="one approval per required role"):
        PrimaryPromotionAuthorizationRequest.model_validate(payload)


def test_changed_intent_rejected(tmp_path):
    request = build_request(tmp_path)
    payload = request.model_dump(mode="json")
    payload["deployment"]["deployment_generation"] = 5
    with pytest.raises(ValidationError):
        PrimaryPromotionAuthorizationRequest.model_validate(payload)


def test_subject_mismatch_rejected(tmp_path):
    request = build_request(tmp_path)
    payload = request.model_dump(mode="json")
    payload["p10"]["subject"]["model_id"] = "changed-model"
    with pytest.raises(ValidationError, match="does not match active canary"):
        PrimaryPromotionAuthorizationRequest.model_validate(payload)


def test_activation_id_mismatch_rejected(tmp_path):
    request = build_request(tmp_path)
    payload = request.model_dump(mode="json")
    payload["p10"]["p9_activation_id"] = "0" * 64
    with pytest.raises(ValidationError, match="activation ID"):
        PrimaryPromotionAuthorizationRequest.model_validate(payload)


def test_authorization_seal_tamper_rejected(tmp_path):
    _, authorization = issue(tmp_path)
    authorization["target_primary"]["subject"]["model_id"] = "tampered"
    with pytest.raises(ValueError, match="seal mismatch"):
        verify_authorization_seal(authorization)


def test_transaction_guard_success(tmp_path):
    _, authorization = issue(tmp_path)
    transaction = transaction_from(authorization)
    validate_primary_promotion_transaction(
        authorization,
        transaction,
        consumed_authorization_ids=set(),
        consumed_transaction_nonces=set(),
        observed_deployment_state_sha256=(
            authorization["expected_deployment_state_sha256"]
        ),
        now_utc="2026-08-05T10:27:00Z",
    )


def test_transaction_guard_stale_state_rejected(tmp_path):
    _, authorization = issue(tmp_path)
    transaction = transaction_from(authorization)
    with pytest.raises(ValueError, match="compare-and-swap"):
        validate_primary_promotion_transaction(
            authorization,
            transaction,
            consumed_authorization_ids=set(),
            consumed_transaction_nonces=set(),
            observed_deployment_state_sha256="0" * 64,
            now_utc="2026-08-05T10:27:00Z",
        )


def test_transaction_guard_consumed_authorization_rejected(tmp_path):
    _, authorization = issue(tmp_path)
    transaction = transaction_from(authorization)
    with pytest.raises(ValueError, match="authorization ID already consumed"):
        validate_primary_promotion_transaction(
            authorization,
            transaction,
            consumed_authorization_ids={authorization["authorization_id"]},
            consumed_transaction_nonces=set(),
            observed_deployment_state_sha256=(
                authorization["expected_deployment_state_sha256"]
            ),
            now_utc="2026-08-05T10:27:00Z",
        )


def test_transaction_guard_consumed_nonce_rejected(tmp_path):
    _, authorization = issue(tmp_path)
    transaction = transaction_from(authorization)
    with pytest.raises(ValueError, match="transaction nonce already consumed"):
        validate_primary_promotion_transaction(
            authorization,
            transaction,
            consumed_authorization_ids=set(),
            consumed_transaction_nonces={transaction.transaction_nonce},
            observed_deployment_state_sha256=(
                authorization["expected_deployment_state_sha256"]
            ),
            now_utc="2026-08-05T10:27:00Z",
        )


def test_transaction_guard_expired_rejected(tmp_path):
    _, authorization = issue(tmp_path)
    transaction = transaction_from(authorization)
    with pytest.raises(ValueError, match="authorization expired"):
        validate_primary_promotion_transaction(
            authorization,
            transaction,
            consumed_authorization_ids=set(),
            consumed_transaction_nonces=set(),
            observed_deployment_state_sha256=(
                authorization["expected_deployment_state_sha256"]
            ),
            now_utc="2026-08-05T10:41:00Z",
        )


@pytest.mark.parametrize(
    "field,new_value,match",
    [
        ("deployment_target", "file+json:///tmp/other.json", "deployment_target"),
        ("expected_deployment_state_sha256", "1" * 64, "deployment_state"),
        ("target_primary", {"changed": True}, "target_primary"),
        ("expected_canary_before", {"changed": True}, "expected_canary"),
    ],
)
def test_transaction_exact_binding_rejected(
    tmp_path,
    field,
    new_value,
    match,
):
    _, authorization = issue(tmp_path)
    payload = transaction_from(authorization).model_dump(mode="json")
    payload[field] = new_value
    transaction = PrimaryPromotionTransactionRequest.model_validate(payload)
    with pytest.raises(ValueError, match=match):
        validate_primary_promotion_transaction(
            authorization,
            transaction,
            consumed_authorization_ids=set(),
            consumed_transaction_nonces=set(),
            observed_deployment_state_sha256=(
                authorization["expected_deployment_state_sha256"]
            ),
            now_utc="2026-08-05T10:27:00Z",
        )
