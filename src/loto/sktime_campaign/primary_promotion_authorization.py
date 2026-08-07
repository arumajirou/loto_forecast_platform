from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ACKNOWLEDGEMENTS = (
    "P10_METRICS_AND_BASELINES_REVIEWED",
    "REAL_PROSPECTIVE_CHRONOLOGY_REVIEWED",
    "RUNTIME_AND_ARTIFACT_IDENTITY_REVIEWED",
    "PRIMARY_IMPACT_AND_ROLLBACK_REVIEWED",
    "MONITORING_AND_ABORT_THRESHOLDS_REVIEWED",
)
REQUIRED_ROLES = ("model_owner", "independent_reviewer", "operations_owner")
SSH_NAMESPACE = "loto-sktime-p11"


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


class RegisteredSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registry_target: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    shadow_candidate_id: str = Field(min_length=1)
    model_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeploymentBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: RegisteredSubject
    activated_at_utc: str
    activation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_p8_transaction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["primary", "shadow_canary"]

    @model_validator(mode="after")
    def validate_time(self) -> "DeploymentBinding":
        _parse_utc(self.activated_at_utc, label="activated_at_utc")
        return self


class P10ReviewEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    p10_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p10_decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p10_aggregated_metrics_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p10_baseline_comparison_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p10_window_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p9_activation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW"]
    eligible_for_primary_promotion_review: Literal[True] = True
    primary_promotion_executed: Literal[False] = False
    primary_binding_changed: Literal[False] = False
    prediction_publication_allowed: Literal[False] = False
    weighted_hit_at_1: float = Field(ge=0.0, le=1.0)
    worst_window_hit_at_1: float = Field(ge=0.0, le=1.0)
    weighted_all_position_hit_at_1: float = Field(ge=0.0, le=1.0)
    weighted_mae: float = Field(ge=0.0)
    weighted_mse: float = Field(ge=0.0)
    weighted_rmse: float = Field(ge=0.0)
    window_count: int = Field(ge=3)
    draw_count: int = Field(ge=3)
    subject: RegisteredSubject


class DeploymentPrecondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    deployment_target: str = Field(min_length=1)
    deployment_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    deployment_generation: int = Field(ge=1)
    primary_binding: DeploymentBinding | None = None
    canary_binding: DeploymentBinding
    state_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_canary(self) -> "DeploymentPrecondition":
        if self.canary_binding.mode != "shadow_canary":
            raise ValueError("P11 requires an active shadow canary")
        payload = self.model_dump(mode="json", exclude={"state_snapshot_sha256"})
        if canonical_sha256(payload) != self.state_snapshot_sha256:
            raise ValueError("deployment precondition snapshot seal mismatch")
        return self


class PromotionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_ttl_seconds: int = Field(default=1800, ge=300, le=3600)
    required_roles: tuple[str, ...] = REQUIRED_ROLES
    required_acknowledgements: tuple[str, ...] = ACKNOWLEDGEMENTS
    minimum_post_promotion_draws: int = Field(default=3, ge=1)
    minimum_post_promotion_hit_at_1: float = Field(default=0.90, ge=0.0, le=1.0)
    maximum_post_promotion_mae: float = Field(default=1.0, ge=0.0)
    clear_canary_on_commit: Literal[True] = True
    automatic_primary_promotion: Literal[False] = False
    automatic_retraining: Literal[False] = False
    automatic_rollback: Literal[False] = False
    prediction_publication_allowed_before_p12: Literal[False] = False

    @model_validator(mode="after")
    def validate_policy(self) -> "PromotionPolicy":
        if self.required_roles != REQUIRED_ROLES:
            raise ValueError("required roles must match the formal P11 inventory")
        if self.required_acknowledgements != ACKNOWLEDGEMENTS:
            raise ValueError(
                "required acknowledgements must match the formal P11 inventory"
            )
        return self


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    role: Literal["model_owner", "independent_reviewer", "operations_owner"]
    approver_id: str = Field(min_length=1)
    signer_identity: str = Field(min_length=1)
    approved_at_utc: str
    intent_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledgements: tuple[str, ...]
    rationale: str = Field(min_length=10)
    signature_base64: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_approval(self) -> "ApprovalRecord":
        _parse_utc(self.approved_at_utc, label="approved_at_utc")
        if self.acknowledgements != ACKNOWLEDGEMENTS:
            raise ValueError("approval acknowledgements mismatch")
        try:
            base64.b64decode(self.signature_base64, validate=True)
        except ValueError as exc:
            raise ValueError("signature_base64 is invalid") from exc
        return self


class PrimaryPromotionAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["authorize_primary_promotion"] = (
        "authorize_primary_promotion"
    )
    output_dir: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_signers_file: str = Field(min_length=1)
    allowed_signers_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_at_utc: str
    expires_at_utc: str
    authorization_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    p10: P10ReviewEvidence
    deployment: DeploymentPrecondition
    policy: PromotionPolicy
    approvals: tuple[ApprovalRecord, ...]

    @model_validator(mode="after")
    def validate_request(self) -> "PrimaryPromotionAuthorizationRequest":
        requested = _parse_utc(
            self.requested_at_utc,
            label="requested_at_utc",
        )
        expires = _parse_utc(self.expires_at_utc, label="expires_at_utc")
        ttl = int((expires - requested).total_seconds())
        if ttl <= 0 or ttl > self.policy.authorization_ttl_seconds:
            raise ValueError("authorization TTL exceeds policy")
        if self.p10.subject != self.deployment.canary_binding.subject:
            raise ValueError("P10 subject does not match active canary")
        if self.p10.p9_activation_id != self.deployment.canary_binding.activation_id:
            raise ValueError("P10 activation ID does not match active canary")
        roles = tuple(item.role for item in self.approvals)
        if tuple(sorted(roles)) != tuple(sorted(REQUIRED_ROLES)):
            raise ValueError("exactly one approval per required role is required")
        approvers = {item.approver_id for item in self.approvals}
        signers = {item.signer_identity for item in self.approvals}
        if len(approvers) != len(REQUIRED_ROLES):
            raise ValueError("approver IDs must be distinct")
        if len(signers) != len(REQUIRED_ROLES):
            raise ValueError("signer identities must be distinct")
        intent_hash = canonical_sha256(primary_promotion_intent(self))
        for approval in self.approvals:
            if approval.intent_sha256 != intent_hash:
                raise ValueError("approval intent SHA mismatch")
            approved = _parse_utc(
                approval.approved_at_utc,
                label="approved_at_utc",
            )
            if approved < requested or approved > expires:
                raise ValueError("approval timestamp is outside authorization window")
        return self


def primary_promotion_intent(
    request: PrimaryPromotionAuthorizationRequest,
) -> dict[str, Any]:
    deployment = request.deployment
    return {
        "schema_version": "1.0",
        "operation": request.operation,
        "run_id": request.run_id,
        "requested_at_utc": request.requested_at_utc,
        "expires_at_utc": request.expires_at_utc,
        "authorization_nonce": request.authorization_nonce,
        "p10": request.p10.model_dump(mode="json"),
        "deployment": deployment.model_dump(mode="json"),
        "expected_primary_before": (
            deployment.primary_binding.model_dump(mode="json")
            if deployment.primary_binding
            else None
        ),
        "expected_canary_before": deployment.canary_binding.model_dump(
            mode="json"
        ),
        "target_primary": deployment.canary_binding.model_copy(
            update={"mode": "primary"}
        ).model_dump(mode="json"),
        "clear_canary_on_commit": True,
        "rollback_target": (
            deployment.primary_binding.model_dump(mode="json")
            if deployment.primary_binding
            else None
        ),
        "monitoring": {
            "minimum_post_promotion_draws": (
                request.policy.minimum_post_promotion_draws
            ),
            "minimum_post_promotion_hit_at_1": (
                request.policy.minimum_post_promotion_hit_at_1
            ),
            "maximum_post_promotion_mae": (
                request.policy.maximum_post_promotion_mae
            ),
            "automatic_rollback": False,
        },
        "allowed_signers_sha256": request.allowed_signers_sha256,
        "code_sha256": request.code_sha256,
        "config_sha256": request.config_sha256,
    }


SignatureVerifier = Callable[
    [ApprovalRecord, bytes, Path, str],
    tuple[bool, str],
]


def ssh_signature_verifier(
    approval: ApprovalRecord,
    payload: bytes,
    allowed_signers_file: Path,
    namespace: str,
) -> tuple[bool, str]:
    signature = base64.b64decode(approval.signature_base64)
    with tempfile.TemporaryDirectory(prefix="sktime-p11-signature-") as tmp:
        signature_path = Path(tmp) / "signature"
        signature_path.write_bytes(signature)
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
                namespace,
                "-s",
                str(signature_path),
            ],
            input=payload,
            capture_output=True,
            check=False,
        )
    detail = (
        completed.stdout.decode("utf-8", errors="replace")
        + completed.stderr.decode("utf-8", errors="replace")
    ).strip()
    return completed.returncode == 0, detail


def _authorization_payload(
    request: PrimaryPromotionAuthorizationRequest,
    *,
    issued_at_utc: str,
) -> dict[str, Any]:
    intent = primary_promotion_intent(request)
    intent_sha = canonical_sha256(intent)
    authorization_id = canonical_sha256(
        {
            "intent_sha256": intent_sha,
            "authorization_nonce": request.authorization_nonce,
            "issued_at_utc": issued_at_utc,
        }
    )
    return {
        "schema_version": "1.0",
        "decision": "AUTHORIZED_FOR_ONE_PRIMARY_PROMOTION_TRANSACTION",
        "authorization_id": authorization_id,
        "authorization_nonce": request.authorization_nonce,
        "issued_at_utc": issued_at_utc,
        "expires_at_utc": request.expires_at_utc,
        "intent_sha256": intent_sha,
        "p10_bundle_sha256": request.p10.p10_bundle_sha256,
        "deployment_target": request.deployment.deployment_target,
        "expected_deployment_state_sha256": (
            request.deployment.deployment_state_sha256
        ),
        "expected_primary_before": intent["expected_primary_before"],
        "expected_canary_before": intent["expected_canary_before"],
        "target_primary": intent["target_primary"],
        "clear_canary_on_commit": True,
        "rollback_target": intent["rollback_target"],
        "monitoring": intent["monitoring"],
        "one_time": True,
        "consumed": False,
        "primary_promotion_authorized": True,
        "primary_promotion_executed": False,
        "primary_binding_changed": False,
        "canary_binding_changed": False,
        "prediction_publication_allowed": False,
        "automatic_primary_promotion": False,
        "automatic_retraining": False,
        "automatic_rollback": False,
    }


def issue_primary_promotion_authorization(
    request: PrimaryPromotionAuthorizationRequest,
    *,
    issued_at_utc: str,
    signature_verifier: SignatureVerifier,
) -> dict[str, Any]:
    issued = _parse_utc(issued_at_utc, label="issued_at_utc")
    requested = _parse_utc(
        request.requested_at_utc,
        label="requested_at_utc",
    )
    expires = _parse_utc(request.expires_at_utc, label="expires_at_utc")
    if issued < requested or issued > expires:
        raise ValueError("authorization issuance is outside the valid window")
    allowed_signers = Path(request.allowed_signers_file)
    if not allowed_signers.is_file():
        raise ValueError("allowed signers file is missing")
    digest = hashlib.sha256(allowed_signers.read_bytes()).hexdigest()
    if digest != request.allowed_signers_sha256:
        raise ValueError("allowed signers SHA mismatch")
    intent = primary_promotion_intent(request)
    payload = canonical_json_bytes(intent)
    verification: list[dict[str, Any]] = []
    for approval in request.approvals:
        ok, detail = signature_verifier(
            approval,
            payload,
            allowed_signers,
            SSH_NAMESPACE,
        )
        verification.append(
            {
                "role": approval.role,
                "approver_id": approval.approver_id,
                "signer_identity": approval.signer_identity,
                "verified": ok,
                "detail": detail,
            }
        )
        if not ok:
            raise ValueError(
                f"signature verification failed for role {approval.role}"
            )
    authorization = _authorization_payload(
        request,
        issued_at_utc=issued_at_utc,
    )
    authorization["seal_sha256"] = canonical_sha256(authorization)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "stage": "P11_PRIMARY_PROMOTION_AUTHORIZATION",
        "decision": authorization["decision"],
        "signature_verification": verification,
        "authorization": authorization,
        "promotion_status": "APPROVED_NOT_PRIMARY",
        "next_action": "P12_ATOMIC_PRIMARY_PROMOTION_TRANSACTION",
    }


class PrimaryPromotionTransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    authorization_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_seal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_at_utc: str
    deployment_target: str = Field(min_length=1)
    expected_deployment_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_primary_before: dict[str, Any] | None
    expected_canary_before: dict[str, Any]
    target_primary: dict[str, Any]
    clear_canary_on_commit: Literal[True] = True

    @model_validator(mode="after")
    def validate_time(self) -> "PrimaryPromotionTransactionRequest":
        _parse_utc(self.requested_at_utc, label="requested_at_utc")
        return self


def verify_authorization_seal(authorization: dict[str, Any]) -> None:
    seal = authorization.get("seal_sha256")
    payload = {key: value for key, value in authorization.items() if key != "seal_sha256"}
    if seal != canonical_sha256(payload):
        raise ValueError("primary promotion authorization seal mismatch")


def validate_primary_promotion_transaction(
    authorization: dict[str, Any],
    transaction: PrimaryPromotionTransactionRequest,
    *,
    consumed_authorization_ids: set[str],
    consumed_transaction_nonces: set[str],
    observed_deployment_state_sha256: str,
    now_utc: str,
) -> None:
    verify_authorization_seal(authorization)
    if authorization.get("decision") != (
        "AUTHORIZED_FOR_ONE_PRIMARY_PROMOTION_TRANSACTION"
    ):
        raise ValueError("authorization decision mismatch")
    if authorization.get("primary_promotion_authorized") is not True:
        raise ValueError("primary promotion is not authorized")
    if authorization.get("primary_promotion_executed") is not False:
        raise ValueError("authorization already records execution")
    if authorization.get("one_time") is not True:
        raise ValueError("authorization is not one-time")
    if authorization.get("consumed") is not False:
        raise ValueError("authorization is already consumed")
    now = _parse_utc(now_utc, label="now_utc")
    expires = _parse_utc(
        str(authorization["expires_at_utc"]),
        label="expires_at_utc",
    )
    if now > expires:
        raise ValueError("primary promotion authorization expired")
    exact = {
        "authorization_id": authorization["authorization_id"],
        "authorization_seal_sha256": authorization["seal_sha256"],
        "deployment_target": authorization["deployment_target"],
        "expected_deployment_state_sha256": (
            authorization["expected_deployment_state_sha256"]
        ),
        "expected_primary_before": authorization["expected_primary_before"],
        "expected_canary_before": authorization["expected_canary_before"],
        "target_primary": authorization["target_primary"],
        "clear_canary_on_commit": authorization["clear_canary_on_commit"],
    }
    transaction_payload = transaction.model_dump(mode="json")
    for label, expected in exact.items():
        if transaction_payload[label] != expected:
            raise ValueError(f"primary promotion transaction changed {label}")
    if (
        transaction.expected_deployment_state_sha256
        != observed_deployment_state_sha256
    ):
        raise ValueError("deployment state compare-and-swap precondition failed")
    if transaction.authorization_id in consumed_authorization_ids:
        raise ValueError("authorization ID already consumed")
    if transaction.transaction_nonce in consumed_transaction_nonces:
        raise ValueError("transaction nonce already consumed")
