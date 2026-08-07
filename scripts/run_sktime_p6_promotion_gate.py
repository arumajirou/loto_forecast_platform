from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.promotion_artifacts import persist_p6
from loto.sktime_campaign.promotion_gate import PromotionGateRequest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the sktime P6 manual promotion eligibility gate."
    )
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
    payload["output_dir"] = args.output
    request = PromotionGateRequest.model_validate(payload)
    response = persist_p6(request)
    print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
