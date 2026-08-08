from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

P18_SCHEMA = "autogluon-manual-approval-authorization-v1"
SIGNATURE_NAMESPACE = "loto-autogluon-p18"
REQUIRED_ROLES = ("model_owner", "independent_reviewer")
REQUIRED_RISKS = (
    "REAL_PROSPECTIVE_ACCURACY_REVIEWED",
    "ALL_BASELINE_COMPARISONS_REVIEWED",
    "LEAKAGE_AND_EVIDENCE_INTEGRITY_REVIEWED",
    "ROLLBACK_AND_REGISTRY_PLAN_REVIEWED",
)


class ApprovalAuthorizationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def parse_utc(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ApprovalAuthorizationError(
            "UTC_TIMESTAMP_INVALID",
            f"{label} must use YYYY-MM-DDTHH:MM:SSZ",
        ) from exc
    return parsed.replace(tzinfo=timezone.utc)


class P17EligibilityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    p17_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p17_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p17_run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    selected_candidate_id: str = Field(min_length=1)
    decision: Literal["ELIGIBLE_FOR_HUMAN_APPROVAL"]
    status: Literal["PASS"] = "PASS"
    reason_code: Literal["ALL_RULES_PASS"] = "ALL_RULES_PASS"
    human_approval_required: Literal[True] = True
    human_approval_granted: Literal[False] = False
    automatic_promotion: Literal[False] = False
    automatic_retraining: Literal[False] = False
    registry_write_allowed: Literal[False] = False
    promotion_status: Literal["NOT_PROMOTED"] = "NOT_PROMOTED"


class RegistrySubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_target: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    selected_candidate_id: str = Field(min_length=1)
    model_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("registry_target")
    @classmethod
    def registry_target_is_immutable(cls, value: str) -> str:
        lowered = value.lower()
        if any(token in lowered for token in ("latest", "champion", "production")):
            raise ValueError("registry target must identify an exact immutable destination")
        return value


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    required_roles: tuple[Literal["model_owner", "independent_reviewer"], ...] = REQUIRED_ROLES
    required_risk_acknowledgements: tuple[str, ...] = REQUIRED_RISKS
    authorization_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    require_distinct_approvers: Literal[True] = True
    require_distinct_signers: Literal[True] = True
    signature_scheme: Literal["ssh-ed25519"] = "ssh-ed25519"
    signature_namespace: Literal["loto-autogluon-p18"] = SIGNATURE_NAMESPACE
    one_time_use: Literal[True] = True
    automatic_promotion: Literal[False] = False
    automatic_retraining: Literal[False] = False

    @model_validator(mode="after")
    def validate_inventory(self) -> "ApprovalPolicy":
        if self.required_roles != REQUIRED_ROLES:
            raise ValueError("required role order and inventory must remain fixed")
        if self.required_risk_acknowledgements != REQUIRED_RISKS:
            raise ValueError("risk acknowledgement inventory must remain fixed")
        return self


class ApprovalIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["autogluon-p18-approval-intent-v1"] = "autogluon-p18-approval-intent-v1"
    operation: Literal["issue_one_time_registry_authorization"] = (
        "issue_one_time_registry_authorization"
    )
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    approval_requested_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    authorization_expires_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    authorization_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_signers_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_signer_identities: tuple[str, str]
    p17: P17EligibilityEvidence
    subject: RegistrySubject
    policy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    registry_write_executed: Literal[False] = False
    automatic_promotion: Literal[False] = False
    automatic_retraining: Literal[False] = False
    intent_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_intent(self) -> "ApprovalIntent":
        requested = parse_utc(
            self.approval_requested_at_utc,
            label="approval_requested_at_utc",
        )
        expires = parse_utc(
            self.authorization_expires_at_utc,
            label="authorization_expires_at_utc",
        )
        lifetime = int((expires - requested).total_seconds())
        if lifetime <= 0:
            raise ValueError("authorization expiry must follow request time")
        if lifetime > self.policy.authorization_ttl_seconds:
            raise ValueError("authorization lifetime exceeds policy")
        if self.subject.selected_candidate_id != self.p17.selected_candidate_id:
            raise ValueError("registry subject changed P17 selected candidate")
        if len(set(self.allowed_signer_identities)) != 2:
            raise ValueError("allowed signer identities must be distinct")
        expected = canonical_sha256(approval_intent_payload(self, include_hash=False))
        if self.intent_sha256 != expected:
            raise ValueError("approval intent SHA-256 mismatch")
        return self


class ApprovalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["autogluon-p18-approval-draft-v1"] = "autogluon-p18-approval-draft-v1"
    role: Literal["model_owner", "independent_reviewer"]
    approver_id: str = Field(pattern=r"^[A-Za-z0-9._@-]+$", min_length=2)
    signer_identity: str = Field(pattern=r"^[A-Za-z0-9._@-]+$", min_length=2)
    approved_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    decision: Literal["APPROVE"] = "APPROVE"
    approval_intent_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_namespace: Literal["loto-autogluon-p18"] = SIGNATURE_NAMESPACE
    risk_acknowledgements: tuple[str, ...] = REQUIRED_RISKS
    rationale: str = Field(min_length=20, max_length=2000)
    signed_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_draft(self) -> "ApprovalDraft":
        parse_utc(self.approved_at_utc, label="approved_at_utc")
        if self.risk_acknowledgements != REQUIRED_RISKS:
            raise ValueError("approval risk acknowledgement inventory mismatch")
        expected = canonical_sha256(approval_signing_payload(self))
        if self.signed_payload_sha256 != expected:
            raise ValueError("approval signing payload SHA-256 mismatch")
        return self


class HumanApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    draft: ApprovalDraft
    signature: str = Field(min_length=32)


SignatureVerifier = Callable[[HumanApproval, bytes], bool]


def approval_intent_payload(
    intent: ApprovalIntent | Mapping[str, Any],
    *,
    include_hash: bool = False,
) -> dict[str, Any]:
    if isinstance(intent, ApprovalIntent):
        payload = intent.model_dump(mode="json")
    else:
        payload = dict(intent)
    if not include_hash:
        payload.pop("intent_sha256", None)
    return payload


def approval_signing_payload(draft: ApprovalDraft | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(draft, ApprovalDraft):
        payload = draft.model_dump(mode="json")
    else:
        payload = dict(draft)
    payload.pop("signed_payload_sha256", None)
    return payload


def make_approval_intent(
    *,
    run_id: str,
    git_commit: str,
    requested_at_utc: str,
    expires_at_utc: str,
    authorization_nonce: str,
    allowed_signers_sha256: str,
    allowed_signer_identities: tuple[str, str],
    p17: P17EligibilityEvidence,
    subject: RegistrySubject,
    policy: ApprovalPolicy,
) -> ApprovalIntent:
    payload = {
        "schema_version": "autogluon-p18-approval-intent-v1",
        "operation": "issue_one_time_registry_authorization",
        "run_id": run_id,
        "git_commit": git_commit,
        "approval_requested_at_utc": requested_at_utc,
        "authorization_expires_at_utc": expires_at_utc,
        "authorization_nonce": authorization_nonce,
        "allowed_signers_sha256": allowed_signers_sha256,
        "allowed_signer_identities": list(allowed_signer_identities),
        "p17": p17.model_dump(mode="json"),
        "subject": subject.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
    }
    payload["intent_sha256"] = canonical_sha256(payload)
    return ApprovalIntent.model_validate(payload)


def prepare_approval_draft(
    *,
    intent: ApprovalIntent,
    role: Literal["model_owner", "independent_reviewer"],
    approver_id: str,
    signer_identity: str,
    approved_at_utc: str,
    rationale: str,
) -> ApprovalDraft:
    approved = parse_utc(approved_at_utc, label="approved_at_utc")
    requested = parse_utc(
        intent.approval_requested_at_utc,
        label="approval_requested_at_utc",
    )
    expires = parse_utc(
        intent.authorization_expires_at_utc,
        label="authorization_expires_at_utc",
    )
    if approved < requested or approved > expires:
        raise ApprovalAuthorizationError(
            "APPROVAL_OUTSIDE_WINDOW",
            approved_at_utc,
        )
    payload = {
        "schema_version": "autogluon-p18-approval-draft-v1",
        "role": role,
        "approver_id": approver_id,
        "signer_identity": signer_identity,
        "approved_at_utc": approved_at_utc,
        "decision": "APPROVE",
        "approval_intent_sha256": intent.intent_sha256,
        "signature_namespace": SIGNATURE_NAMESPACE,
        "risk_acknowledgements": list(REQUIRED_RISKS),
        "rationale": rationale,
    }
    payload["signed_payload_sha256"] = canonical_sha256(payload)
    return ApprovalDraft.model_validate(payload)


def make_ssh_signature_verifier(allowed_signers_file: Path) -> SignatureVerifier:
    allowed_signers_file = allowed_signers_file.resolve()

    def verify(approval: HumanApproval, payload: bytes) -> bool:
        with tempfile.TemporaryDirectory(prefix="autogluon-p18-signature-") as tmp:
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
                    approval.draft.signer_identity,
                    "-n",
                    SIGNATURE_NAMESPACE,
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
    *,
    intent: ApprovalIntent,
    approvals: Sequence[HumanApproval],
    verified_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> list[dict[str, Any]]:
    verified_at = parse_utc(verified_at_utc, label="verified_at_utc")
    requested = parse_utc(
        intent.approval_requested_at_utc,
        label="approval_requested_at_utc",
    )
    expires = parse_utc(
        intent.authorization_expires_at_utc,
        label="authorization_expires_at_utc",
    )
    if verified_at < requested:
        raise ApprovalAuthorizationError(
            "VERIFICATION_PRECEDES_REQUEST",
            verified_at_utc,
        )
    if verified_at > expires:
        raise ApprovalAuthorizationError("AUTHORIZATION_EXPIRED", verified_at_utc)
    if len(approvals) != len(REQUIRED_ROLES):
        raise ApprovalAuthorizationError(
            "APPROVAL_COUNT_MISMATCH",
            str(len(approvals)),
        )
    roles = tuple(approval.draft.role for approval in approvals)
    if tuple(sorted(roles)) != tuple(sorted(REQUIRED_ROLES)):
        raise ApprovalAuthorizationError("APPROVAL_ROLE_MISMATCH", str(roles))
    approvers = tuple(approval.draft.approver_id for approval in approvals)
    if len(set(approvers)) != len(approvers):
        raise ApprovalAuthorizationError("APPROVERS_NOT_DISTINCT", str(approvers))
    signers = tuple(approval.draft.signer_identity for approval in approvals)
    if len(set(signers)) != len(signers):
        raise ApprovalAuthorizationError("SIGNERS_NOT_DISTINCT", str(signers))
    if set(signers) != set(intent.allowed_signer_identities):
        raise ApprovalAuthorizationError(
            "SIGNER_NOT_ALLOWED",
            str(signers),
        )

    evidence = []
    for approval in approvals:
        draft = approval.draft
        if draft.approval_intent_sha256 != intent.intent_sha256:
            raise ApprovalAuthorizationError(
                "APPROVAL_INTENT_MISMATCH",
                draft.role,
            )
        approved = parse_utc(draft.approved_at_utc, label="approved_at_utc")
        if approved < requested or approved > expires:
            raise ApprovalAuthorizationError(
                "APPROVAL_OUTSIDE_WINDOW",
                draft.approved_at_utc,
            )
        payload = canonical_json_bytes(approval_signing_payload(draft))
        if hashlib.sha256(payload).hexdigest() != draft.signed_payload_sha256:
            raise ApprovalAuthorizationError(
                "SIGNED_PAYLOAD_HASH_MISMATCH",
                draft.role,
            )
        if not signature_verifier(approval, payload):
            raise ApprovalAuthorizationError(
                "SIGNATURE_VERIFICATION_FAILED",
                draft.role,
            )
        evidence.append(
            {
                "role": draft.role,
                "approver_id": draft.approver_id,
                "signer_identity": draft.signer_identity,
                "approved_at_utc": draft.approved_at_utc,
                "signed_payload_sha256": draft.signed_payload_sha256,
                "signature_verification_status": "PASS",
            }
        )
    return evidence


def issue_registry_authorization(
    *,
    intent: ApprovalIntent,
    approvals: Sequence[HumanApproval],
    issued_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    signature_evidence = verify_approval_ceremony(
        intent=intent,
        approvals=approvals,
        verified_at_utc=issued_at_utc,
        signature_verifier=signature_verifier,
    )
    authorization_id = canonical_sha256(
        {
            "run_id": intent.run_id,
            "authorization_nonce": intent.authorization_nonce,
            "approval_intent_sha256": intent.intent_sha256,
        }
    )
    core = {
        "schema_version": P18_SCHEMA,
        "status": "PASS",
        "decision": "AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION",
        "authorization_scope": "ONE_EXACT_REGISTRY_TRANSACTION",
        "authorization_id": authorization_id,
        "issued_at_utc": issued_at_utc,
        "expires_at_utc": intent.authorization_expires_at_utc,
        "approval_intent_sha256": intent.intent_sha256,
        "p17_bundle_sha256": intent.p17.p17_bundle_sha256,
        "p17_decision_sha256": intent.p17.p17_decision_sha256,
        "selected_candidate_id": intent.p17.selected_candidate_id,
        "subject": intent.subject.model_dump(mode="json"),
        "approval_evidence": signature_evidence,
        "authorization_nonce": intent.authorization_nonce,
        "one_time_use": True,
        "consumed": False,
        "human_approval_granted": True,
        "registry_write_authorized": True,
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "APPROVED_NOT_REGISTERED",
    }
    authorization = {**core, "seal_sha256": canonical_sha256(core)}
    verify_registry_authorization(authorization)
    return authorization, signature_evidence


def verify_registry_authorization(authorization: Mapping[str, Any]) -> None:
    payload = dict(authorization)
    seal = str(payload.pop("seal_sha256", ""))
    if len(seal) != 64 or canonical_sha256(payload) != seal:
        raise ApprovalAuthorizationError(
            "AUTHORIZATION_SEAL_MISMATCH",
            seal,
        )
    required = {
        "status": "PASS",
        "decision": "AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION",
        "authorization_scope": "ONE_EXACT_REGISTRY_TRANSACTION",
        "one_time_use": True,
        "consumed": False,
        "human_approval_granted": True,
        "registry_write_authorized": True,
        "registry_write_executed": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "APPROVED_NOT_REGISTERED",
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ApprovalAuthorizationError(
                "AUTHORIZATION_STATE_INVALID",
                key,
            )
    if len(payload.get("approval_evidence", [])) != 2:
        raise ApprovalAuthorizationError(
            "AUTHORIZATION_APPROVAL_COUNT_INVALID",
            str(payload.get("approval_evidence")),
        )


__all__ = [
    "ApprovalAuthorizationError",
    "ApprovalDraft",
    "ApprovalIntent",
    "ApprovalPolicy",
    "HumanApproval",
    "P17EligibilityEvidence",
    "RegistrySubject",
    "SIGNATURE_NAMESPACE",
    "canonical_json_bytes",
    "canonical_sha256",
    "issue_registry_authorization",
    "make_approval_intent",
    "make_ssh_signature_verifier",
    "prepare_approval_draft",
    "verify_approval_ceremony",
    "verify_registry_authorization",
]
