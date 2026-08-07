from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from loto.autogluon_campaign.approval_authorization import (
    build_approval_intent,
    create_approval_authorization,
    verify_approval_authorization,
)
from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalAuthorizationError,
    ApprovalDraft,
    ApprovalIntent,
    ApprovalPolicy,
    HumanApproval,
    RegistrySubject,
    canonical_json_bytes,
    make_ssh_signature_verifier,
    prepare_approval_draft,
)
from loto.autogluon_campaign.approval_authorization_io import load_json, write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_policy(path: Path) -> ApprovalPolicy:
    return ApprovalPolicy.model_validate(load_json(path))


def _load_subject(path: Path) -> RegistrySubject:
    return RegistrySubject.model_validate(load_json(path))


def _intent(args: argparse.Namespace) -> int:
    requested = args.requested_at_utc or _utc_now()
    requested_dt = datetime.strptime(requested, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    policy = _load_policy(args.policy)
    expires = args.expires_at_utc or (
        requested_dt + timedelta(seconds=policy.authorization_ttl_seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    intent = build_approval_intent(
        p17_evidence_dir=args.p17,
        subject=_load_subject(args.subject),
        policy=policy,
        allowed_signers_file=args.allowed_signers,
        run_id=args.run_id,
        git_commit=args.git_commit,
        requested_at_utc=requested,
        expires_at_utc=expires,
        authorization_nonce=args.authorization_nonce or secrets.token_hex(32),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, intent.model_dump(mode="json"))
    print(json.dumps({"status": "PASS", "intent": str(args.output),
                      "intent_sha256": intent.intent_sha256}, sort_keys=True))
    return 0


def _prepare(args: argparse.Namespace) -> int:
    intent = ApprovalIntent.model_validate(load_json(args.intent))
    draft = prepare_approval_draft(
        intent=intent,
        role=args.role,
        approver_id=args.approver_id,
        signer_identity=args.signer_identity,
        approved_at_utc=args.approved_at_utc or _utc_now(),
        rationale=args.rationale,
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / "approval-draft.json", draft.model_dump(mode="json"))
    (args.output_dir / "approval-signing-payload.bin").write_bytes(
        canonical_json_bytes(
            {
                key: value
                for key, value in draft.model_dump(mode="json").items()
                if key != "signed_payload_sha256"
            }
        )
    )
    print(json.dumps({"status": "PASS", "output_dir": str(args.output_dir)}, sort_keys=True))
    return 0


def _finalize(args: argparse.Namespace) -> int:
    draft = ApprovalDraft.model_validate(load_json(args.draft))
    signature = args.signature.read_text(encoding="utf-8")
    approval = HumanApproval(draft=draft, signature=signature)
    write_json(args.output, approval.model_dump(mode="json"))
    print(json.dumps({"status": "PASS", "approval": str(args.output)}, sort_keys=True))
    return 0


def _authorize(args: argparse.Namespace) -> int:
    intent = ApprovalIntent.model_validate(load_json(args.intent))
    approvals = [
        HumanApproval.model_validate(load_json(path)) for path in args.approval
    ]
    verifier = make_ssh_signature_verifier(args.allowed_signers)
    result = create_approval_authorization(
        p17_evidence_dir=args.p17,
        intent=intent,
        approvals=approvals,
        allowed_signers_file=args.allowed_signers,
        output_dir=args.output,
        issued_at_utc=args.issued_at_utc or _utc_now(),
        signature_verifier=verifier,
    )
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


def _verify(args: argparse.Namespace) -> int:
    result = verify_approval_authorization(args.run)
    print(json.dumps(result, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoGluon P18 manual approval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    intent = subparsers.add_parser("intent")
    intent.add_argument("--p17", type=Path, required=True)
    intent.add_argument("--subject", type=Path, required=True)
    intent.add_argument("--policy", type=Path, required=True)
    intent.add_argument("--allowed-signers", type=Path, required=True)
    intent.add_argument("--run-id", required=True)
    intent.add_argument("--git-commit", required=True)
    intent.add_argument("--requested-at-utc")
    intent.add_argument("--expires-at-utc")
    intent.add_argument("--authorization-nonce")
    intent.add_argument("--output", type=Path, required=True)
    intent.set_defaults(handler=_intent)

    prepare = subparsers.add_parser("prepare-approval")
    prepare.add_argument("--intent", type=Path, required=True)
    prepare.add_argument(
        "--role",
        choices=("model_owner", "independent_reviewer"),
        required=True,
    )
    prepare.add_argument("--approver-id", required=True)
    prepare.add_argument("--signer-identity", required=True)
    prepare.add_argument("--approved-at-utc")
    prepare.add_argument("--rationale", required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.set_defaults(handler=_prepare)

    finalize = subparsers.add_parser("finalize-approval")
    finalize.add_argument("--draft", type=Path, required=True)
    finalize.add_argument("--signature", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)
    finalize.set_defaults(handler=_finalize)

    authorize = subparsers.add_parser("authorize")
    authorize.add_argument("--p17", type=Path, required=True)
    authorize.add_argument("--intent", type=Path, required=True)
    authorize.add_argument("--approval", type=Path, action="append", required=True)
    authorize.add_argument("--allowed-signers", type=Path, required=True)
    authorize.add_argument("--issued-at-utc")
    authorize.add_argument("--output", type=Path, required=True)
    authorize.set_defaults(handler=_authorize)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--run", type=Path, required=True)
    verify.set_defaults(handler=_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.handler(args))
    except (ApprovalAuthorizationError, ValueError, OSError) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        print(json.dumps({"status": "FAILED", "error_code": code,
                          "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
