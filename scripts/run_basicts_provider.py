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

    parser = argparse.ArgumentParser(description="Run one isolated BasicTS provider request")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.request.read_text(encoding="utf-8"))

    if payload.get("schema_version") == "1.0":
        from loto.basicts_campaign.protocol import ProviderRequest, ProviderStatus
        from loto.basicts_campaign.runtime import execute_request

        request = ProviderRequest.model_validate(payload)
        response = execute_request(request)
        return 0 if response.status is ProviderStatus.PASS else 2

    from loto.basicts_campaign.contracts import BasicTSProviderRequest
    from loto.basicts_campaign.provenance import atomic_write_json
    from loto.basicts_campaign.provider import process_request

    request = BasicTSProviderRequest.model_validate(payload)
    response = process_request(request)
    response_path = args.response or Path(request.artifact_dir) / "response.json"
    atomic_write_json(response_path, response.model_dump(mode="json"))
    return 0 if response.status.value in {"PASS", "PARTIAL", "UNAVAILABLE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
