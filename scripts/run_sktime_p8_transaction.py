from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.registry_artifacts import persist_p8
from loto.sktime_campaign.registry_transaction import P8RegistryTransactionRequest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--committed-at-utc", required=True)
    args = parser.parse_args()
    request = P8RegistryTransactionRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    response = persist_p8(request, committed_at_utc=args.committed_at_utc)
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
