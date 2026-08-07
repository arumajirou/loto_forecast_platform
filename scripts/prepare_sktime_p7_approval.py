from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.approval_authorization import (
    HumanApproval,
    approval_signing_payload,
    canonical_json_bytes,
    canonical_sha256,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument(
        "--role",
        choices=["model_owner", "independent_reviewer"],
        required=True,
    )
    parser.add_argument("--approver-id", required=True)
    parser.add_argument("--signer-identity", required=True)
    parser.add_argument("--approved-at-utc", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    intent = json.loads(args.intent.read_text(encoding="utf-8"))
    intent_sha256 = canonical_sha256(intent)
    approval = HumanApproval(
        role=args.role,
        approver_id=args.approver_id,
        signer_identity=args.signer_identity,
        approved_at_utc=args.approved_at_utc,
        approval_intent_sha256=intent_sha256,
        signed_payload_sha256="0" * 64,
        signature="UNSIGNED-PLACEHOLDER-01234567890123456789",
        risk_acknowledgements=intent["policy"][
            "required_risk_acknowledgements"
        ],
        rationale=args.rationale,
    )
    signing_payload = approval_signing_payload(approval)
    signed_payload_sha256 = canonical_sha256(signing_payload)
    approval = approval.model_copy(
        update={"signed_payload_sha256": signed_payload_sha256}
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    draft_path = args.output_dir / "approval-draft.json"
    payload_path = args.output_dir / "approval-signing-payload.bin"
    draft_path.write_text(
        json.dumps(
            approval.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    payload_path.write_bytes(canonical_json_bytes(signing_payload))
    print(f"SKTIME_P7_APPROVAL_DRAFT={draft_path}")
    print(f"SKTIME_P7_SIGNING_PAYLOAD={payload_path}")
    print(f"SKTIME_P7_SIGNED_PAYLOAD_SHA256={signed_payload_sha256}")


if __name__ == "__main__":
    main()
