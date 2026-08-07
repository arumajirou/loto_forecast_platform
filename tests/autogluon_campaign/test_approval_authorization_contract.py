from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.autogluon_campaign.approval_authorization import build_approval_intent
from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalAuthorizationError,
    ApprovalPolicy,
    HumanApproval,
    RegistrySubject,
    issue_registry_authorization,
    prepare_approval_draft,
    verify_approval_ceremony,
    verify_registry_authorization,
)
from loto.autogluon_campaign.approval_authorization_io import read_p17_eligibility
from tests.autogluon_campaign.p18_test_support import (
    always_verify,
    make_allowed_signers,
    make_approvals,
    make_intent,
    make_p17_bundle,
    make_subject,
)


def test_eligible_p17_bundle_is_bound_to_intent(tmp_path: Path) -> None:
    p17, signers, intent = make_intent(tmp_path)
    evidence = read_p17_eligibility(p17)
    assert intent.p17 == evidence
    assert intent.allowed_signers_sha256
    assert signers.is_file()
    assert intent.subject.selected_candidate_id == evidence.selected_candidate_id


def test_not_eligible_p17_bundle_is_rejected(tmp_path: Path) -> None:
    p17 = make_p17_bundle(
        tmp_path / "p17",
        decision_value="NOT_ELIGIBLE",
        reason_code="ALL_WINDOWS_STABLE",
    )
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        read_p17_eligibility(p17)
    assert exc_info.value.code == "P17_NOT_ELIGIBLE"


def test_p17_tampering_is_rejected(tmp_path: Path) -> None:
    p17 = make_p17_bundle(tmp_path / "p17")
    path = p17 / "PROMOTION_DECISION.json"
    path.write_text(path.read_text().replace("ALL_RULES_PASS", "TAMPERED"))
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        read_p17_eligibility(p17)
    assert exc_info.value.code == "SHA256_MISMATCH"


def test_p17_symlink_is_rejected(tmp_path: Path) -> None:
    p17 = make_p17_bundle(tmp_path / "p17")
    (p17 / "unsafe-link").symlink_to(p17 / "response.json")
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        read_p17_eligibility(p17)
    assert exc_info.value.code == "SYMLINK_FORBIDDEN"


def test_subject_candidate_mismatch_is_rejected(tmp_path: Path) -> None:
    p17 = make_p17_bundle(tmp_path / "p17")
    signers = make_allowed_signers(tmp_path / "allowed_signers")
    with pytest.raises(ValidationError):
        build_approval_intent(
            p17_evidence_dir=p17,
            subject=make_subject("DeepAR-known-static"),
            policy=ApprovalPolicy(),
            allowed_signers_file=signers,
            run_id="p18",
            git_commit="0e17956",
            requested_at_utc="2026-08-05T10:00:00Z",
            expires_at_utc="2026-08-05T11:00:00Z",
            authorization_nonce="a" * 64,
        )


def test_mutable_registry_target_is_rejected() -> None:
    payload = make_subject().model_dump()
    payload["registry_target"] = "mlflow://registry/champion"
    with pytest.raises(ValidationError):
        RegistrySubject.model_validate(payload)


def test_authorization_lifetime_over_policy_is_rejected(tmp_path: Path) -> None:
    p17 = make_p17_bundle(tmp_path / "p17")
    signers = make_allowed_signers(tmp_path / "allowed_signers")
    with pytest.raises(ValidationError):
        build_approval_intent(
            p17_evidence_dir=p17,
            subject=make_subject(),
            policy=ApprovalPolicy(),
            allowed_signers_file=signers,
            run_id="p18",
            git_commit="0e17956",
            requested_at_utc="2026-08-05T10:00:00Z",
            expires_at_utc="2026-08-05T12:00:00Z",
            authorization_nonce="a" * 64,
        )


def test_approval_outside_window_is_rejected(tmp_path: Path) -> None:
    _, _, intent = make_intent(tmp_path)
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        prepare_approval_draft(
            intent=intent,
            role="model_owner",
            approver_id="owner@example",
            signer_identity="owner@example",
            approved_at_utc="2026-08-05T11:01:00Z",
            rationale="This rationale is deliberately long enough for the contract.",
        )
    assert exc_info.value.code == "APPROVAL_OUTSIDE_WINDOW"


def test_duplicate_approver_is_rejected(tmp_path: Path) -> None:
    _, _, intent = make_intent(tmp_path)
    approvals = make_approvals(intent)
    duplicate = approvals[1].model_copy(
        update={
            "draft": approvals[1].draft.model_copy(
                update={"approver_id": approvals[0].draft.approver_id}
            )
        }
    )
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_ceremony(
            intent=intent,
            approvals=[approvals[0], duplicate],
            verified_at_utc="2026-08-05T10:30:00Z",
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "APPROVERS_NOT_DISTINCT"


def test_duplicate_signer_is_rejected(tmp_path: Path) -> None:
    _, _, intent = make_intent(tmp_path)
    approvals = make_approvals(intent)
    duplicate = approvals[1].model_copy(
        update={
            "draft": approvals[1].draft.model_copy(
                update={"signer_identity": approvals[0].draft.signer_identity}
            )
        }
    )
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_ceremony(
            intent=intent,
            approvals=[approvals[0], duplicate],
            verified_at_utc="2026-08-05T10:30:00Z",
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "SIGNERS_NOT_DISTINCT"


def test_expired_authorization_is_rejected(tmp_path: Path) -> None:
    _, _, intent = make_intent(tmp_path)
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_ceremony(
            intent=intent,
            approvals=make_approvals(intent),
            verified_at_utc="2026-08-05T11:00:01Z",
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "AUTHORIZATION_EXPIRED"


def test_signature_failure_is_rejected(tmp_path: Path) -> None:
    _, _, intent = make_intent(tmp_path)
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_ceremony(
            intent=intent,
            approvals=make_approvals(intent),
            verified_at_utc="2026-08-05T10:30:00Z",
            signature_verifier=lambda _approval, _payload: False,
        )
    assert exc_info.value.code == "SIGNATURE_VERIFICATION_FAILED"


def test_successful_authorization_never_executes_registry_write(tmp_path: Path) -> None:
    _, _, intent = make_intent(tmp_path)
    authorization, evidence = issue_registry_authorization(
        intent=intent,
        approvals=make_approvals(intent),
        issued_at_utc="2026-08-05T10:30:00Z",
        signature_verifier=always_verify,
    )
    assert len(evidence) == 2
    assert authorization["decision"] == "AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION"
    assert authorization["registry_write_authorized"] is True
    assert authorization["registry_write_executed"] is False
    assert authorization["promotion_status"] == "APPROVED_NOT_REGISTERED"
    assert authorization["consumed"] is False


def test_authorization_seal_tampering_is_rejected(tmp_path: Path) -> None:
    _, _, intent = make_intent(tmp_path)
    authorization, _ = issue_registry_authorization(
        intent=intent,
        approvals=make_approvals(intent),
        issued_at_utc="2026-08-05T10:30:00Z",
        signature_verifier=always_verify,
    )
    authorization["registry_write_executed"] = True
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_registry_authorization(authorization)
    assert exc_info.value.code == "AUTHORIZATION_SEAL_MISMATCH"


def test_non_ed25519_allowed_signer_is_rejected(tmp_path: Path) -> None:
    p17 = make_p17_bundle(tmp_path / "p17")
    signers = tmp_path / "allowed_signers"
    signers.write_text(
        "owner@example ssh-rsa b3duZXIta2V5\n"
        "reviewer@example ssh-ed25519 cmV2aWV3ZXIta2V5\n",
        encoding="utf-8",
    )
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        build_approval_intent(
            p17_evidence_dir=p17,
            subject=make_subject(),
            policy=ApprovalPolicy(),
            allowed_signers_file=signers,
            run_id="p18",
            git_commit="0e17956",
            requested_at_utc="2026-08-05T10:00:00Z",
            expires_at_utc="2026-08-05T11:00:00Z",
            authorization_nonce="a" * 64,
        )
    assert exc_info.value.code == "ALLOWED_SIGNER_KEY_TYPE_INVALID"


def test_duplicate_allowed_signer_key_is_rejected(tmp_path: Path) -> None:
    p17 = make_p17_bundle(tmp_path / "p17")
    signers = tmp_path / "allowed_signers"
    signers.write_text(
        "owner@example ssh-ed25519 c2FtZS1rZXk=\n"
        "reviewer@example ssh-ed25519 c2FtZS1rZXk=\n",
        encoding="utf-8",
    )
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        build_approval_intent(
            p17_evidence_dir=p17,
            subject=make_subject(),
            policy=ApprovalPolicy(),
            allowed_signers_file=signers,
            run_id="p18",
            git_commit="0e17956",
            requested_at_utc="2026-08-05T10:00:00Z",
            expires_at_utc="2026-08-05T11:00:00Z",
            authorization_nonce="a" * 64,
        )
    assert exc_info.value.code == "ALLOWED_SIGNER_KEY_DUPLICATE"


def test_signer_not_in_frozen_allowed_inventory_is_rejected(tmp_path: Path) -> None:
    _, _, intent = make_intent(tmp_path)
    approvals = make_approvals(intent)
    intruder_draft = prepare_approval_draft(
        intent=intent,
        role="independent_reviewer",
        approver_id="reviewer@example",
        signer_identity="intruder@example",
        approved_at_utc="2026-08-05T10:20:00Z",
        rationale="Independently reviewed all metrics, evidence, and rollback controls.",
    )
    intruder = HumanApproval(
        draft=intruder_draft,
        signature=approvals[1].signature,
    )
    with pytest.raises(ApprovalAuthorizationError) as exc_info:
        verify_approval_ceremony(
            intent=intent,
            approvals=[approvals[0], intruder],
            verified_at_utc="2026-08-05T10:30:00Z",
            signature_verifier=always_verify,
        )
    assert exc_info.value.code == "SIGNER_NOT_ALLOWED"
