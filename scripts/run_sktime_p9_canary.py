from __future__ import annotations

import argparse
from pathlib import Path

from loto.sktime_campaign.deployment_artifacts import persist_p9
from loto.sktime_campaign.deployment_canary import CanaryActivationRequest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--committed-at-utc", required=True)
    args = parser.parse_args()
    request = CanaryActivationRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    response = persist_p9(request, committed_at_utc=args.committed_at_utc)
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
