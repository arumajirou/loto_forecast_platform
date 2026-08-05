from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from loto.sktime_campaign.protocol import ProviderRequest, ProviderStatus
from loto.sktime_campaign.runtime import execute_request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the isolated sktime discovery or Naive smoke provider."
    )
    parser.add_argument("--request", required=True, help="Path to a provider request JSON file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(Path(args.request).read_text(encoding="utf-8"))
        request = ProviderRequest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 2

    response = execute_request(request)
    print(response.model_dump_json(indent=2))
    return 0 if response.status is ProviderStatus.PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
