from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.registry_artifacts import verify_p8
from loto.sktime_campaign.registry_transaction import P8RegistryTransactionRequest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = P8RegistryTransactionRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    result = verify_p8(args.output, request)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
