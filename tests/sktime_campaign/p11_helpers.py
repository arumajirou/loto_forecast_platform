from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace

from loto.sktime_campaign.primary_promotion_authorization import (
    ACKNOWLEDGEMENTS,
    ApprovalRecord,
    DeploymentBinding,
    DeploymentPrecondition,
    P10ReviewEvidence,
    PrimaryPromotionAuthorizationRequest,
    PromotionPolicy,
    RegisteredSubject,
    canonical_sha256,
    primary_promotion_intent,
)

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64
HEX_F = "f" * 64


def subject() -> RegisteredSubject:
    return RegisteredSubject(
        registry_target="file+json:///tmp/registry.json",
        model_id="sktime-candidate",
        model_revision="abcdef1",
        shadow_candidate_id="candidate-1",
        model_artifact_sha256=HEX_A,
        data_snapshot_sha256=HEX_B,
        runtime_environment_sha256=HEX_C,
        code_sha256=HEX_D,
    )


def canary_binding() -> DeploymentBinding:
    return DeploymentBinding(
        subject=subject(),
        activated_at_utc="2026-08-05T10:00:00Z",
        activation_id=HEX_E,
        source_p8_transaction_id=HEX_F,
        mode="shadow_canary",
    )


def primary_binding() -> DeploymentBinding:
    return DeploymentBinding(
        subject=subject().model_copy(
            update={
                "model_id": "current-primary",
                "model_revision": "1234567",
                "shadow_candidate_id": "primary-before",
                "model_artifact_sha256": "1" * 64,
            }
        ),
        activated_at_utc="2026-08-01T10:00:00Z",
        activation_id="2" * 64,
        source_p8_transaction_id="3" * 64,
        mode="primary",
    )


def p10() -> P10ReviewEvidence:
    return P10ReviewEvidence(
        p10_bundle_sha256="4" * 64,
        p10_decision_sha256="5" * 64,
        p10_aggregated_metrics_sha256="6" * 64,
        p10_baseline_comparison_sha256="7" * 64,
        p10_window_evidence_sha256="8" * 64,
        p9_activation_id=HEX_E,
        decision="ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW",
        weighted_hit_at_1=0.95,
        worst_window_hit_at_1=0.90,
        weighted_all_position_hit_at_1=0.80,
        weighted_mae=0.5,
        weighted_mse=0.5,
        weighted_rmse=0.707106,
        window_count=3,
        draw_count=3,
        subject=subject(),
    )


def deployment() -> DeploymentPrecondition:
    payload = {
        "schema_version": "1.0",
        "deployment_target": "file+json:///tmp/deployment.json",
        "deployment_state_sha256": "9" * 64,
        "deployment_generation": 4,
        "primary_binding": primary_binding().model_dump(mode="json"),
        "canary_binding": canary_binding().model_dump(mode="json"),
    }
    return DeploymentPrecondition.model_validate(
        {**payload, "state_snapshot_sha256": canonical_sha256(payload)}
    )


def allowed_signers(tmp_path: Path) -> Path:
    path = tmp_path / "allowed_signers"
    path.write_text(
        "\n".join(
            [
                "owner@example ssh-ed25519 AAAAowner",
                "reviewer@example ssh-ed25519 AAAAreviewer",
                "ops@example ssh-ed25519 AAAAops",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def build_request(tmp_path: Path) -> PrimaryPromotionAuthorizationRequest:
    signers = allowed_signers(tmp_path)
    policy = PromotionPolicy()
    common = {
        "schema_version": "1.0",
        "operation": "authorize_primary_promotion",
        "output_dir": str(tmp_path / "evidence"),
        "run_id": "p11-test",
        "git_commit": "abcdef1",
        "code_sha256": "a1" * 32,
        "config_sha256": "b2" * 32,
        "allowed_signers_file": str(signers),
        "allowed_signers_sha256": hashlib.sha256(signers.read_bytes()).hexdigest(),
        "requested_at_utc": "2026-08-05T10:10:00Z",
        "expires_at_utc": "2026-08-05T10:40:00Z",
        "authorization_nonce": "c3" * 32,
        "p10": p10(),
        "deployment": deployment(),
        "policy": policy,
    }
    placeholder = SimpleNamespace(**common)
    intent_sha = canonical_sha256(primary_promotion_intent(placeholder))
    signature = base64.b64encode(b"fake-signature").decode("ascii")
    approvals = [
        ApprovalRecord(
            role="model_owner",
            approver_id="owner-person",
            signer_identity="owner@example",
            approved_at_utc="2026-08-05T10:20:00Z",
            intent_sha256=intent_sha,
            acknowledgements=ACKNOWLEDGEMENTS,
            rationale="Reviewed metrics, chronology, runtime, impact, and rollback.",
            signature_base64=signature,
        ),
        ApprovalRecord(
            role="independent_reviewer",
            approver_id="reviewer-person",
            signer_identity="reviewer@example",
            approved_at_utc="2026-08-05T10:21:00Z",
            intent_sha256=intent_sha,
            acknowledgements=ACKNOWLEDGEMENTS,
            rationale="Independently reviewed every required promotion control.",
            signature_base64=signature,
        ),
        ApprovalRecord(
            role="operations_owner",
            approver_id="ops-person",
            signer_identity="ops@example",
            approved_at_utc="2026-08-05T10:22:00Z",
            intent_sha256=intent_sha,
            acknowledgements=ACKNOWLEDGEMENTS,
            rationale="Reviewed operational impact, monitoring, and rollback.",
            signature_base64=signature,
        ),
    ]
    return PrimaryPromotionAuthorizationRequest.model_validate({**common, "approvals": approvals})


def fake_verifier(*args):
    return True, "fake signature verified"


def failing_verifier(*args):
    return False, "fake signature rejected"
