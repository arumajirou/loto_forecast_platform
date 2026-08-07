from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalAuthorizationError,
    ApprovalIntent,
    ApprovalPolicy,
    HumanApproval,
    RegistrySubject,
    SignatureVerifier,
    canonical_sha256,
    issue_registry_authorization,
    make_approval_intent,
    make_ssh_signature_verifier,
    verify_approval_ceremony,
    verify_registry_authorization,
)
from loto.autogluon_campaign.approval_authorization_io import (
    approval_output_tree_sha256,
    empty_output_dir,
    file_sha256,
    load_json,
    read_allowed_signers_inventory,
    read_p17_eligibility,
    tree_sha256,
    verify_manifest,
    verify_sha256sums,
    write_evidence,
    write_json,
)

OUTPUT_FILES = {
    "REQUEST_METADATA.json",
    "P17_LINEAGE.json",
    "APPROVAL_INTENT.json",
    "APPROVALS.json",
    "SIGNATURE_VERIFICATION.json",
    "REGISTRY_AUTHORIZATION.json",
    "REGISTRY_TRANSACTION_REQUIREMENTS.json",
    "response.json",
    "ARTIFACT_MANIFEST.json",
    "ALLOWED_SIGNERS",
    "SHA256SUMS",
}


@dataclass(frozen=True)
class ApprovalAuthorizationResult:
    output_dir: str
    authorization_path: str
    status: str
    decision: str
    authorization_id: str
    selected_candidate_id: str


def build_approval_intent(
    *,
    p17_evidence_dir: Path,
    subject: RegistrySubject,
    policy: ApprovalPolicy,
    allowed_signers_file: Path,
    run_id: str,
    git_commit: str,
    requested_at_utc: str,
    expires_at_utc: str,
    authorization_nonce: str,
) -> ApprovalIntent:
    p17 = read_p17_eligibility(p17_evidence_dir)
    signers = allowed_signers_file.resolve()
    signer_identities = read_allowed_signers_inventory(signers)
    return make_approval_intent(
        run_id=run_id,
        git_commit=git_commit,
        requested_at_utc=requested_at_utc,
        expires_at_utc=expires_at_utc,
        authorization_nonce=authorization_nonce,
        allowed_signers_sha256=file_sha256(signers),
        allowed_signer_identities=signer_identities,
        p17=p17,
        subject=subject,
        policy=policy,
    )


def create_approval_authorization(
    *,
    p17_evidence_dir: Path,
    intent: ApprovalIntent,
    approvals: Sequence[HumanApproval],
    allowed_signers_file: Path,
    output_dir: Path,
    issued_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> ApprovalAuthorizationResult:
    source = p17_evidence_dir.resolve()
    before = tree_sha256(source)
    p17 = read_p17_eligibility(source)
    if p17 != intent.p17:
        raise ApprovalAuthorizationError("P17_INTENT_LINEAGE_MISMATCH", str(source))
    signers = allowed_signers_file.resolve()
    if file_sha256(signers) != intent.allowed_signers_sha256:
        raise ApprovalAuthorizationError(
            "ALLOWED_SIGNERS_HASH_MISMATCH",
            str(signers),
        )
    signer_identities = read_allowed_signers_inventory(signers)
    if signer_identities != intent.allowed_signer_identities:
        raise ApprovalAuthorizationError(
            "ALLOWED_SIGNER_IDENTITIES_MISMATCH",
            str(signer_identities),
        )

    authorization, signature_evidence = issue_registry_authorization(
        intent=intent,
        approvals=approvals,
        issued_at_utc=issued_at_utc,
        signature_verifier=signature_verifier,
    )
    root = empty_output_dir(output_dir)
    created_at = datetime.now(timezone.utc).isoformat()
    payloads = {
        "REQUEST_METADATA.json": {
            "schema_version": "autogluon-p18-request-v1",
            "run_id": intent.run_id,
            "created_at": created_at,
            "timestamp_authority": "LOCAL_SYSTEM_UTC",
            "issued_at_utc": issued_at_utc,
        },
        "P17_LINEAGE.json": {
            "p17_run_id": p17.p17_run_id,
            "p17_bundle_sha256": p17.p17_bundle_sha256,
            "p17_decision_sha256": p17.p17_decision_sha256,
            "selected_candidate_id": p17.selected_candidate_id,
        },
        "APPROVAL_INTENT.json": intent.model_dump(mode="json"),
        "APPROVALS.json": {
            "approvals": [approval.model_dump(mode="json") for approval in approvals]
        },
        "SIGNATURE_VERIFICATION.json": {
            "status": "PASS",
            "signature_namespace": intent.policy.signature_namespace,
            "allowed_signers_sha256": intent.allowed_signers_sha256,
            "approvals": signature_evidence,
        },
        "REGISTRY_AUTHORIZATION.json": authorization,
        "REGISTRY_TRANSACTION_REQUIREMENTS.json": {
            "schema_version": "autogluon-p18-transaction-requirements-v1",
            "authorization_id": authorization["authorization_id"],
            "authorization_seal_sha256": authorization["seal_sha256"],
            "expected_subject": intent.subject.model_dump(mode="json"),
            "expected_current_registry_state_sha256_required": True,
            "compare_and_swap_required": True,
            "append_only_consumption_ledger_required": True,
            "authorization_must_be_unexpired": True,
            "authorization_must_be_unconsumed": True,
            "registry_write_executed": False,
        },
        "response.json": {
            "status": authorization["status"],
            "decision": authorization["decision"],
            "authorization_id": authorization["authorization_id"],
            "selected_candidate_id": authorization["selected_candidate_id"],
            "human_approval_granted": True,
            "registry_write_authorized": True,
            "registry_write_executed": False,
            "promotion_status": "APPROVED_NOT_REGISTERED",
        },
    }
    for name, payload in payloads.items():
        write_json(root / name, payload)
    (root / "ALLOWED_SIGNERS").write_bytes(signers.read_bytes())
    write_evidence(root, [*payloads, "ALLOWED_SIGNERS"])
    if tree_sha256(source) != before:
        raise ApprovalAuthorizationError("P17_SOURCE_MUTATED", str(source))
    verify_approval_authorization(root, signature_verifier=signature_verifier)
    return ApprovalAuthorizationResult(
        output_dir=str(root),
        authorization_path=str(root / "REGISTRY_AUTHORIZATION.json"),
        status="PASS",
        decision="AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION",
        authorization_id=str(authorization["authorization_id"]),
        selected_candidate_id=p17.selected_candidate_id,
    )


def verify_approval_authorization(
    root: Path,
    *,
    signature_verifier: SignatureVerifier | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    observed = verify_sha256sums(root)
    if observed != OUTPUT_FILES:
        raise ApprovalAuthorizationError(
            "P18_FILE_SET_MISMATCH",
            str(sorted(observed)),
        )
    verify_manifest(root, OUTPUT_FILES - {"ARTIFACT_MANIFEST.json", "SHA256SUMS"})
    intent = ApprovalIntent.model_validate(load_json(root / "APPROVAL_INTENT.json"))
    signers_path = root / "ALLOWED_SIGNERS"
    if file_sha256(signers_path) != intent.allowed_signers_sha256:
        raise ApprovalAuthorizationError("ALLOWED_SIGNERS_HASH_MISMATCH", str(root))
    signer_identities = read_allowed_signers_inventory(signers_path)
    if signer_identities != intent.allowed_signer_identities:
        raise ApprovalAuthorizationError(
            "ALLOWED_SIGNER_IDENTITIES_MISMATCH",
            str(root),
        )
    authorization = load_json(root / "REGISTRY_AUTHORIZATION.json")
    verify_registry_authorization(authorization)
    lineage = load_json(root / "P17_LINEAGE.json")
    expected_lineage = {
        "p17_run_id": intent.p17.p17_run_id,
        "p17_bundle_sha256": intent.p17.p17_bundle_sha256,
        "p17_decision_sha256": intent.p17.p17_decision_sha256,
        "selected_candidate_id": intent.p17.selected_candidate_id,
    }
    if lineage != expected_lineage:
        raise ApprovalAuthorizationError("P17_LINEAGE_MISMATCH", str(root))
    signatures = load_json(root / "SIGNATURE_VERIFICATION.json")
    if signatures.get("status") != "PASS":
        raise ApprovalAuthorizationError("SIGNATURE_STATUS_INVALID", str(root))
    if signatures.get("allowed_signers_sha256") != intent.allowed_signers_sha256:
        raise ApprovalAuthorizationError("SIGNER_LINEAGE_MISMATCH", str(root))
    approval_payload = load_json(root / "APPROVALS.json")
    approval_rows = approval_payload.get("approvals")
    if not isinstance(approval_rows, list) or len(approval_rows) != 2:
        raise ApprovalAuthorizationError("APPROVALS_INVALID", str(root))
    approvals = [HumanApproval.model_validate(row) for row in approval_rows]
    request_metadata = load_json(root / "REQUEST_METADATA.json")
    verifier = signature_verifier or make_ssh_signature_verifier(signers_path)
    recomputed_signatures = verify_approval_ceremony(
        intent=intent,
        approvals=approvals,
        verified_at_utc=str(request_metadata["issued_at_utc"]),
        signature_verifier=verifier,
    )
    if signatures.get("approvals") != recomputed_signatures:
        raise ApprovalAuthorizationError("SIGNATURE_EVIDENCE_MISMATCH", str(root))
    transaction = load_json(root / "REGISTRY_TRANSACTION_REQUIREMENTS.json")
    if transaction.get("authorization_id") != authorization["authorization_id"]:
        raise ApprovalAuthorizationError("TRANSACTION_AUTHORIZATION_MISMATCH", str(root))
    if transaction.get("authorization_seal_sha256") != authorization["seal_sha256"]:
        raise ApprovalAuthorizationError("TRANSACTION_SEAL_MISMATCH", str(root))
    if transaction.get("expected_subject") != intent.subject.model_dump(mode="json"):
        raise ApprovalAuthorizationError("TRANSACTION_SUBJECT_MISMATCH", str(root))
    response = load_json(root / "response.json")
    expected_response = {
        "status": "PASS",
        "decision": "AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION",
        "authorization_id": authorization["authorization_id"],
        "selected_candidate_id": authorization["selected_candidate_id"],
        "human_approval_granted": True,
        "registry_write_authorized": True,
        "registry_write_executed": False,
        "promotion_status": "APPROVED_NOT_REGISTERED",
    }
    if response != expected_response:
        raise ApprovalAuthorizationError("P18_RESPONSE_MISMATCH", str(root))
    return {
        "status": "PASS",
        "decision": authorization["decision"],
        "authorization_id": authorization["authorization_id"],
        "authorization_seal_sha256": authorization["seal_sha256"],
        "approval_intent_sha256": intent.intent_sha256,
        "tree_sha256": approval_output_tree_sha256(root),
        "registry_write_executed": False,
    }


__all__ = [
    "ApprovalAuthorizationResult",
    "build_approval_intent",
    "create_approval_authorization",
    "verify_approval_authorization",
]
