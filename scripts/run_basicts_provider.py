from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.basicts_campaign.protocol import ProviderRequest, ProviderStatus
from loto.basicts_campaign.runtime import execute_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated BasicTS provider")
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.request.read_text(encoding="utf-8"))
    request = ProviderRequest.model_validate(payload)
    response = execute_request(request)
    print(response.model_dump_json(indent=2))
    return 0 if response.status is ProviderStatus.PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
