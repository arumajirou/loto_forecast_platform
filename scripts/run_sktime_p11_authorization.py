from __future__ import annotations

import argparse
from pathlib import Path

from loto.sktime_campaign.primary_promotion_artifacts import persist_p11
from loto.sktime_campaign.primary_promotion_authorization import (
    PrimaryPromotionAuthorizationRequest,
    ssh_signature_verifier,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--issued-at-utc", required=True)
    args = parser.parse_args()
    request = PrimaryPromotionAuthorizationRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    response = persist_p11(
        request,
        issued_at_utc=args.issued_at_utc,
        signature_verifier=ssh_signature_verifier,
    )
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
