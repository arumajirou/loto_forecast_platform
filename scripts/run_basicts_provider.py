from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.basicts_campaign.contracts import BasicTSProviderRequest
from loto.basicts_campaign.provenance import atomic_write_json
from loto.basicts_campaign.provider import process_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one isolated BasicTS provider request")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.request.read_text(encoding="utf-8"))
    request = BasicTSProviderRequest.model_validate(payload)
    response = process_request(request)
    atomic_write_json(args.response, response.model_dump(mode="json"))
    return 0 if response.status.value in {"PASS", "PARTIAL", "UNAVAILABLE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
