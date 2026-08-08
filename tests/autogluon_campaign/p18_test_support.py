from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from loto.autogluon_campaign.approval_authorization import build_approval_intent
from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalIntent,
    ApprovalPolicy,
    HumanApproval,
    RegistrySubject,
    canonical_sha256,
    prepare_approval_draft,
)
from loto.autogluon_campaign.approval_authorization_io import (
    write_evidence,
    write_json,
)


def make_p17_bundle(
    root: Path,
    *,
    decision_value: str = "ELIGIBLE_FOR_HUMAN_APPROVAL",
    reason_code: str = "ALL_RULES_PASS",
    candidate_id: str = "TFT-known-past-static",
) -> Path:
    root.mkdir(parents=True)
    decision_core: dict[str, Any] = {
        "schema_version": "autogluon-promotion-eligibility-v1",
        "status": "PASS",
        "decision": decision_value,
        "reason_code": reason_code,
        "selected_candidate_id": candidate_id,
        "human_approval_required": True,
        "human_approval_granted": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "registry_write_allowed": False,
        "promotion_status": "NOT_PROMOTED",
    }
    decision = {
        **decision_core,
        "decision_sha256": canonical_sha256(decision_core),
    }
    payloads = {
        "REQUEST_METADATA.json": {
            "schema_version": "autogluon-promotion-eligibility-v1",
            "run_id": "p17-real-eligible",
            "created_at": "2026-08-05T09:00:00+00:00",
            "timestamp_authority": "LOCAL_SYSTEM_UTC",
            "policy": {},
        },
        "UPSTREAM_LINEAGE.json": {"holdout": {}, "prospective": []},
        "WINDOW_EVIDENCE.json": {"holdout": {}, "prospective": []},
        "AGGREGATED_METRICS.json": {"selected_candidate_id": candidate_id},
        "RULE_EVALUATION.json": {"rules": []},
        "PROMOTION_DECISION.json": decision,
        "response.json": {
            "status": "PASS",
            "decision": decision_value,
            "reason_code": reason_code,
            "selected_candidate_id": candidate_id,
            "registry_write_allowed": False,
        },
    }
    for name, payload in payloads.items():
        write_json(root / name, payload)
    write_evidence(root, list(payloads))
    return root


def make_allowed_signers(path: Path) -> Path:
    owner_key = base64.b64encode(b"owner-ed25519-public-key").decode("ascii")
    reviewer_key = base64.b64encode(b"reviewer-ed25519-public-key").decode("ascii")
    path.write_text(
        f"owner@example ssh-ed25519 {owner_key}\nreviewer@example ssh-ed25519 {reviewer_key}\n",
        encoding="utf-8",
    )
    return path


def make_subject(candidate_id: str = "TFT-known-past-static") -> RegistrySubject:
    return RegistrySubject(
        registry_target="file+json:///mnt/e/registry/autogluon-20260805.json",
        model_id="autogluon-timeseries-shadow",
        model_revision="0123456789abcdef",
        selected_candidate_id=candidate_id,
        model_artifact_sha256="1" * 64,
        data_snapshot_sha256="2" * 64,
        runtime_environment_sha256="3" * 64,
        code_sha256="4" * 64,
        config_sha256="5" * 64,
    )


def make_intent(tmp_path: Path) -> tuple[Path, Path, ApprovalIntent]:
    p17 = make_p17_bundle(tmp_path / "p17")
    signers = make_allowed_signers(tmp_path / "allowed_signers")
    intent = build_approval_intent(
        p17_evidence_dir=p17,
        subject=make_subject(),
        policy=ApprovalPolicy(),
        allowed_signers_file=signers,
        run_id="p18-approval-20260805",
        git_commit="0e17956cef83f7b8e866c16def361d8769f76ba7",
        requested_at_utc="2026-08-05T10:00:00Z",
        expires_at_utc="2026-08-05T11:00:00Z",
        authorization_nonce="a" * 64,
    )
    return p17, signers, intent


def make_approvals(intent: ApprovalIntent) -> list[HumanApproval]:
    owner = prepare_approval_draft(
        intent=intent,
        role="model_owner",
        approver_id="owner@example",
        signer_identity="owner@example",
        approved_at_utc="2026-08-05T10:10:00Z",
        rationale="Reviewed prospective accuracy and all required risk evidence.",
    )
    reviewer = prepare_approval_draft(
        intent=intent,
        role="independent_reviewer",
        approver_id="reviewer@example",
        signer_identity="reviewer@example",
        approved_at_utc="2026-08-05T10:20:00Z",
        rationale="Independently reviewed baselines, leakage, and rollback evidence.",
    )
    signature = (
        "-----BEGIN SSH SIGNATURE-----\nfake-signature-material\n-----END SSH SIGNATURE-----"
    )
    return [
        HumanApproval(draft=owner, signature=signature),
        HumanApproval(draft=reviewer, signature=signature),
    ]


def always_verify(_approval: HumanApproval, _payload: bytes) -> bool:
    return True
