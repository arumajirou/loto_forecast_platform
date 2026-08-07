from __future__ import annotations

import argparse
from pathlib import Path

from loto.sktime_campaign.primary_promotion_artifacts import verify_p11
from loto.sktime_campaign.primary_promotion_authorization import (
    PrimaryPromotionAuthorizationRequest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    request = PrimaryPromotionAuthorizationRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    result = verify_p11(args.evidence_dir, request)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
