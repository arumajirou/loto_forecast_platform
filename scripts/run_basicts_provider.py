from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"


def main() -> int:
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    from loto.basicts_campaign.protocol import ProviderRequest, ProviderStatus
    from loto.basicts_campaign.runtime import execute_request

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
