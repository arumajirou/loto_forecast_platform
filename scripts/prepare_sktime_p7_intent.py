from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_sktime_p7_request import _load_json, _p6_evidence, _sha256

from loto.sktime_campaign.approval_authorization import (
    ApprovalAuthorizationRequest,
    approval_intent_payload,
    canonical_sha256,
)


def _dummy_approvals(
    requested_at_utc: str,
    risks: list[str],
) -> list[dict[str, Any]]:
    common = {
        "approved_at_utc": requested_at_utc,
        "approval_intent_sha256": "0" * 64,
        "signed_payload_sha256": "0" * 64,
        "signature": "UNSIGNED-PLACEHOLDER-01234567890123456789",
        "risk_acknowledgements": risks,
        "rationale": "Unsigned placeholder used only to calculate approval intent.",
    }
    return [
        {
            **common,
            "role": "model_owner",
            "approver_id": "intent-owner-placeholder",
            "signer_identity": "intent-owner-placeholder",
        },
        {
            **common,
            "role": "independent_reviewer",
            "approver_id": "intent-reviewer-placeholder",
            "signer_identity": "intent-reviewer-placeholder",
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p6-dir", type=Path, required=True)
    parser.add_argument("--policy-config", type=Path, required=True)
    parser.add_argument("--subject-config", type=Path, required=True)
    parser.add_argument("--allowed-signers", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence-output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--requested-at-utc", required=True)
    parser.add_argument("--expires-at-utc", required=True)
    parser.add_argument("--authorization-nonce", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    p6 = _p6_evidence(args.p6_dir.resolve())
    policy = _load_json(args.policy_config)
    subject = _load_json(args.subject_config)
    if subject.get("shadow_candidate_id") != p6["shadow_candidate_id"]:
        raise RuntimeError("registry subject differs from P6 shadow candidate")
    payload = {
        "output_dir": args.evidence_output_dir,
        "run_id": args.run_id,
        "git_commit": args.git_commit,
        "code_sha256": args.code_sha256,
        "config_sha256": args.config_sha256,
        "allowed_signers_sha256": _sha256(args.allowed_signers),
        "approval_requested_at_utc": args.requested_at_utc,
        "authorization_expires_at_utc": args.expires_at_utc,
        "authorization_nonce": args.authorization_nonce,
        "p6": p6,
        "subject": subject,
        "policy": policy,
        "approvals": _dummy_approvals(
            args.requested_at_utc,
            list(policy["required_risk_acknowledgements"]),
        ),
    }
    request = ApprovalAuthorizationRequest.model_validate(payload)
    intent = approval_intent_payload(request)
    intent_sha256 = canonical_sha256(intent)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "APPROVAL_INTENT.json").write_text(
        json.dumps(intent, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "APPROVAL_INTENT_SHA256").write_text(
        intent_sha256 + "\n",
        encoding="utf-8",
    )
    print(f"SKTIME_P7_APPROVAL_INTENT={args.output_dir / 'APPROVAL_INTENT.json'}")
    print(f"SKTIME_P7_APPROVAL_INTENT_SHA256={intent_sha256}")


if __name__ == "__main__":
    main()
