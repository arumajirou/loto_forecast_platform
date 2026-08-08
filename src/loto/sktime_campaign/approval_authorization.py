from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_REQUIRED_RISKS = [
    "REAL_PROSPECTIVE_ACCURACY_REVIEWED",
    "BASELINE_COMPARISON_REVIEWED",
    "LEAKAGE_AND_INTEGRITY_REVIEWED",
    "ROLLBACK_PLAN_REVIEWED",
]


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _parse_utc(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{label} must use strict UTC Z format") from exc


class P6EligibilityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    p6_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p6_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p6_run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    shadow_candidate_id: str = Field(min_length=1)
    decision: Literal["ELIGIBLE_FOR_HUMAN_APPROVAL"]
    eligible_for_human_approval: Literal[True] = True
    human_approval_required: Literal[True] = True
    human_approval_granted: Literal[False] = False
    registry_write_allowed: Literal[False] = False
    promotion_status: Literal["NOT_PROMOTED"] = "NOT_PROMOTED"


class RegistrySubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_target: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    shadow_candidate_id: str = Field(min_length=1)
    model_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_roles: list[Literal["model_owner", "independent_reviewer"]] = Field(
        default_factory=lambda: [
            "model_owner",
            "independent_reviewer",
        ],
        min_length=2,
    )
    required_risk_acknowledgements: list[str] = Field(
        default_factory=lambda: list(_REQUIRED_RISKS),
        min_length=4,
    )
    authorization_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    require_distinct_approvers: Literal[True] = True
    require_distinct_signers: Literal[True] = True
    signature_scheme: Literal["ssh-ed25519"] = "ssh-ed25519"
    signature_namespace: Literal["loto-sktime-p7"] = "loto-sktime-p7"
    one_time_use: Literal[True] = True

    @model_validator(mode="after")
    def validate_policy(self) -> "ApprovalPolicy":
        if set(self.required_roles) != {
            "model_owner",
            "independent_reviewer",
        }:
            raise ValueError("required roles must be model owner and reviewer")
        if len(self.required_roles) != len(set(self.required_roles)):
            raise ValueError("required roles must be unique")
        if set(self.required_risk_acknowledgements) != set(_REQUIRED_RISKS):
            raise ValueError("required risk acknowledgement inventory mismatch")
        return self


class HumanApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    role: Literal["model_owner", "independent_reviewer"]
    approver_id: str = Field(pattern=r"^[A-Za-z0-9._@-]+$", min_length=2)
    signer_identity: str = Field(pattern=r"^[A-Za-z0-9._@-]+$", min_length=2)
    approved_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    decision: Literal["APPROVE"] = "APPROVE"
    approval_intent_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_namespace: Literal["loto-sktime-p7"] = "loto-sktime-p7"
    signature: str = Field(min_length=32)
    risk_acknowledgements: list[str] = Field(min_length=4)
    rationale: str = Field(min_length=20, max_length=2000)

    @model_validator(mode="after")
    def validate_approval(self) -> "HumanApproval":
        _parse_utc(self.approved_at_utc, label="approved_at_utc")
        if len(self.risk_acknowledgements) != len(set(self.risk_acknowledgements)):
            raise ValueError("risk acknowledgements must be unique")
        return self


class ApprovalAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["issue_registry_authorization"] = "issue_registry_authorization"
    output_dir: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_signers_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_requested_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    authorization_expires_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    authorization_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    p6: P6EligibilityEvidence
    subject: RegistrySubject
    policy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    approvals: list[HumanApproval] = Field(min_length=2)
    registry_write_executed: Literal[False] = False
    automatic_promotion: Literal[False] = False
    automatic_retraining: Literal[False] = False

    @model_validator(mode="after")
    def validate_request(self) -> "ApprovalAuthorizationRequest":
        requested = _parse_utc(
            self.approval_requested_at_utc,
            label="approval_requested_at_utc",
        )
        expires = _parse_utc(
            self.authorization_expires_at_utc,
            label="authorization_expires_at_utc",
        )
        lifetime = int((expires - requested).total_seconds())
        if lifetime <= 0:
            raise ValueError("authorization expiry must follow request time")
        if lifetime > self.policy.authorization_ttl_seconds:
            raise ValueError("authorization lifetime exceeds policy")
        if self.subject.shadow_candidate_id != self.p6.shadow_candidate_id:
            raise ValueError("registry subject changed P6 shadow candidate")
        roles = [approval.role for approval in self.approvals]
        if sorted(roles) != sorted(self.policy.required_roles):
            raise ValueError("approval role inventory mismatch")
        approvers = [approval.approver_id for approval in self.approvals]
        if self.policy.require_distinct_approvers and len(set(approvers)) != len(approvers):
            raise ValueError("approvers must be distinct")
        signers = [approval.signer_identity for approval in self.approvals]
        if self.policy.require_distinct_signers and len(set(signers)) != len(signers):
            raise ValueError("signers must be distinct")
        for approval in self.approvals:
            approved = _parse_utc(
                approval.approved_at_utc,
                label="approved_at_utc",
            )
            if approved < requested or approved > expires:
                raise ValueError("approval timestamp is outside ceremony window")
        return self


SignatureVerifier = Callable[[HumanApproval, bytes], bool]


def approval_intent_payload(
    request: ApprovalAuthorizationRequest,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "operation": request.operation,
        "run_id": request.run_id,
        "git_commit": request.git_commit,
        "code_sha256": request.code_sha256,
        "config_sha256": request.config_sha256,
        "allowed_signers_sha256": request.allowed_signers_sha256,
        "approval_requested_at_utc": request.approval_requested_at_utc,
        "authorization_expires_at_utc": request.authorization_expires_at_utc,
        "authorization_nonce": request.authorization_nonce,
        "p6": request.p6.model_dump(mode="json"),
        "subject": request.subject.model_dump(mode="json"),
        "policy": request.policy.model_dump(mode="json"),
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
    }


def approval_signing_payload(
    approval: HumanApproval,
) -> dict[str, Any]:
    return {
        "schema_version": approval.schema_version,
        "role": approval.role,
        "approver_id": approval.approver_id,
        "signer_identity": approval.signer_identity,
        "approved_at_utc": approval.approved_at_utc,
        "decision": approval.decision,
        "approval_intent_sha256": approval.approval_intent_sha256,
        "signature_namespace": approval.signature_namespace,
        "risk_acknowledgements": approval.risk_acknowledgements,
        "rationale": approval.rationale,
    }


def make_ssh_signature_verifier(
    allowed_signers_file: Path,
) -> SignatureVerifier:
    allowed_signers_file = allowed_signers_file.resolve()

    def verify(approval: HumanApproval, payload: bytes) -> bool:
        with tempfile.TemporaryDirectory(prefix="sktime-p7-signature-") as tmp:
            signature_path = Path(tmp) / "approval.sig"
            signature_path.write_text(approval.signature, encoding="utf-8")
            completed = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed_signers_file),
                    "-I",
                    approval.signer_identity,
                    "-n",
                    approval.signature_namespace,
                    "-s",
                    str(signature_path),
                ],
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        return completed.returncode == 0

    return verify


def verify_approval_ceremony(
    request: ApprovalAuthorizationRequest,
    *,
    verified_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> list[dict[str, Any]]:
    verified_at = _parse_utc(verified_at_utc, label="verified_at_utc")
    requested = _parse_utc(
        request.approval_requested_at_utc,
        label="approval_requested_at_utc",
    )
    expires = _parse_utc(
        request.authorization_expires_at_utc,
        label="authorization_expires_at_utc",
    )
    if verified_at < requested:
        raise ValueError("ceremony verification precedes approval request")
    if verified_at > expires:
        raise ValueError("approval ceremony authorization has expired")
    intent_sha256 = canonical_sha256(approval_intent_payload(request))
    required_risks = set(request.policy.required_risk_acknowledgements)
    evidence: list[dict[str, Any]] = []
    for approval in request.approvals:
        if approval.approval_intent_sha256 != intent_sha256:
            raise ValueError("approval references a different intent")
        if set(approval.risk_acknowledgements) != required_risks:
            raise ValueError("approval risk acknowledgement mismatch")
        signing_payload = approval_signing_payload(approval)
        signing_bytes = canonical_json_bytes(signing_payload)
        expected_payload_sha256 = hashlib.sha256(signing_bytes).hexdigest()
        if approval.signed_payload_sha256 != expected_payload_sha256:
            raise ValueError("signed approval payload SHA-256 mismatch")
        if not signature_verifier(approval, signing_bytes):
            raise ValueError("approval signature verification failed")
        evidence.append(
            {
                "role": approval.role,
                "approver_id": approval.approver_id,
                "signer_identity": approval.signer_identity,
                "approved_at_utc": approval.approved_at_utc,
                "signed_payload_sha256": approval.signed_payload_sha256,
                "signature_verification_status": "PASS",
            }
        )
    return evidence


def verify_registry_authorization(authorization: dict[str, Any]) -> None:
    seal = str(authorization.get("seal_sha256", ""))
    payload = {key: value for key, value in authorization.items() if key != "seal_sha256"}
    if len(seal) != 64 or canonical_sha256(payload) != seal:
        raise ValueError("registry authorization seal mismatch")
    if authorization.get("registry_write_authorized") is not True:
        raise ValueError("registry authorization is not enabled")
    if authorization.get("registry_write_executed") is not False:
        raise ValueError("P7 authorization incorrectly claims registry write")
    if authorization.get("one_time_use") is not True:
        raise ValueError("registry authorization must be one-time use")
    if authorization.get("consumed") is not False:
        raise ValueError("new authorization must be unconsumed")
    if authorization.get("automatic_promotion") is not False:
        raise ValueError("automatic promotion must remain disabled")
    if authorization.get("automatic_retraining") is not False:
        raise ValueError("automatic retraining must remain disabled")
    if authorization.get("promotion_status") != "APPROVED_NOT_REGISTERED":
        raise ValueError("P7 promotion status mismatch")


def issue_registry_authorization(
    request: ApprovalAuthorizationRequest,
    *,
    issued_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> dict[str, Any]:
    signature_evidence = verify_approval_ceremony(
        request,
        verified_at_utc=issued_at_utc,
        signature_verifier=signature_verifier,
    )
    intent_sha256 = canonical_sha256(approval_intent_payload(request))
    authorization_id = canonical_sha256(
        {
            "run_id": request.run_id,
            "authorization_nonce": request.authorization_nonce,
            "approval_intent_sha256": intent_sha256,
        }
    )
    payload = {
        "schema_version": "1.0",
        "authorization_scope": "ONE_EXACT_REGISTRY_TRANSACTION",
        "authorization_id": authorization_id,
        "issued_at_utc": issued_at_utc,
        "expires_at_utc": request.authorization_expires_at_utc,
        "approval_intent_sha256": intent_sha256,
        "p6_bundle_sha256": request.p6.p6_bundle_sha256,
        "p6_decision_sha256": request.p6.p6_decision_sha256,
        "subject": request.subject.model_dump(mode="json"),
        "approval_evidence": signature_evidence,
        "authorization_nonce": request.authorization_nonce,
        "one_time_use": True,
        "consumed": False,
        "registry_write_authorized": True,
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "APPROVED_NOT_REGISTERED",
    }
    authorization = {**payload, "seal_sha256": canonical_sha256(payload)}
    verify_registry_authorization(authorization)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "stage": "manual_approval_registry_authorization",
        "run_id": request.run_id,
        "authorization": authorization,
        "signature_verification": signature_evidence,
        "decision": "AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION",
        "registry_write_authorized": True,
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "APPROVED_NOT_REGISTERED",
        "next_action": "P8_ATOMIC_REGISTRY_TRANSACTION_REQUIRED",
    }


class RegistryTransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["register_model"] = "register_model"
    authorization_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_seal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    expected_registry_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    subject: RegistrySubject


class AuthorizationConsumptionLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    consumed_authorization_ids: list[str] = Field(default_factory=list)
    consumed_transaction_nonces: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ledger(self) -> "AuthorizationConsumptionLedger":
        if len(self.consumed_authorization_ids) != len(set(self.consumed_authorization_ids)):
            raise ValueError("consumed authorization IDs must be unique")
        if len(self.consumed_transaction_nonces) != len(set(self.consumed_transaction_nonces)):
            raise ValueError("consumed transaction nonces must be unique")
        return self


def validate_registry_transaction_request(
    authorization: dict[str, Any],
    transaction: RegistryTransactionRequest,
    ledger: AuthorizationConsumptionLedger,
    *,
    verified_at_utc: str,
) -> dict[str, Any]:
    verify_registry_authorization(authorization)
    verified_at = _parse_utc(verified_at_utc, label="verified_at_utc")
    issued = _parse_utc(
        str(authorization["issued_at_utc"]),
        label="issued_at_utc",
    )
    expires = _parse_utc(
        str(authorization["expires_at_utc"]),
        label="expires_at_utc",
    )
    requested = _parse_utc(
        transaction.requested_at_utc,
        label="requested_at_utc",
    )
    if not (issued <= requested <= verified_at <= expires):
        raise ValueError("registry transaction is outside authorization window")
    if transaction.authorization_id != authorization["authorization_id"]:
        raise ValueError("registry transaction authorization ID mismatch")
    if transaction.authorization_seal_sha256 != authorization["seal_sha256"]:
        raise ValueError("registry transaction authorization seal mismatch")
    if transaction.subject.model_dump(mode="json") != authorization["subject"]:
        raise ValueError("registry transaction subject differs from authorization")
    if transaction.authorization_id in ledger.consumed_authorization_ids:
        raise ValueError("registry authorization was already consumed")
    if transaction.transaction_nonce in ledger.consumed_transaction_nonces:
        raise ValueError("registry transaction nonce was already consumed")
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "decision": "REGISTRY_TRANSACTION_ALLOWED_ONCE",
        "authorization_id": transaction.authorization_id,
        "transaction_nonce": transaction.transaction_nonce,
        "expected_registry_state_sha256": (transaction.expected_registry_state_sha256),
        "registry_write_executed": False,
        "next_action": "P8_COMPARE_AND_SWAP_REGISTRY_WRITE",
    }
