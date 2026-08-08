from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.primary_promotion_authorization import (
    PrimaryPromotionAuthorizationRequest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-base", required=True, type=Path)
    parser.add_argument("--approval", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.request_base.read_text(encoding="utf-8"))
    payload["approvals"] = [json.loads(path.read_text(encoding="utf-8")) for path in args.approval]
    request = PrimaryPromotionAuthorizationRequest.model_validate(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        request.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
