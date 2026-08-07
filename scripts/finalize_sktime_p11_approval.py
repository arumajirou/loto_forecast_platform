from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from loto.sktime_campaign.primary_promotion_authorization import ApprovalRecord


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.draft.read_text(encoding="utf-8"))
    payload["signature_base64"] = base64.b64encode(
        args.signature.read_bytes()
    ).decode("ascii")
    approval = ApprovalRecord.model_validate(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        approval.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
