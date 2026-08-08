from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.primary_promotion_authorization import (
    ACKNOWLEDGEMENTS,
    canonical_json_bytes,
    canonical_sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument(
        "--role",
        required=True,
        choices=["model_owner", "independent_reviewer", "operations_owner"],
    )
    parser.add_argument("--approver-id", required=True)
    parser.add_argument("--signer-identity", required=True)
    parser.add_argument("--approved-at-utc", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    intent = json.loads(args.intent.read_text(encoding="utf-8"))
    intent_sha = canonical_sha256(intent)
    draft = {
        "schema_version": "1.0",
        "role": args.role,
        "approver_id": args.approver_id,
        "signer_identity": args.signer_identity,
        "approved_at_utc": args.approved_at_utc,
        "intent_sha256": intent_sha,
        "acknowledgements": list(ACKNOWLEDGEMENTS),
        "rationale": args.rationale,
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "approval-draft.json").write_text(
        json.dumps(draft, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "approval-signing-payload.bin").write_bytes(canonical_json_bytes(intent))
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
