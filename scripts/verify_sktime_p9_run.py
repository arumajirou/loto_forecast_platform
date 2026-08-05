from __future__ import annotations

import argparse
from pathlib import Path

from loto.sktime_campaign.deployment_artifacts import verify_p9
from loto.sktime_campaign.deployment_canary import CanaryActivationRequest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    request = CanaryActivationRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    print(verify_p9(args.output, request))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
