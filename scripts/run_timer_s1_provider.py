from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pydantic import ValidationError  # noqa: E402

from loto.adapters.timer_s1.contracts import (  # noqa: E402
    ProviderStatus,
    TimerS1FailureResponse,
    TimerS1Request,
)
from loto.timer_s1_campaign.provider import handle_request  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Timer-S1 PR-A provider skeleton")
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.request.read_text(encoding="utf-8"))
        request = TimerS1Request.model_validate(payload)
        response = handle_request(request)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        run_id = "invalid-request"
        if isinstance(locals().get("payload"), dict):
            run_id = str(payload.get("run_id", run_id))
        response = TimerS1FailureResponse(
            run_id=run_id,
            status=ProviderStatus.FAILED,
            error_code="INVALID_REQUEST",
            error_message=str(exc),
        )
    print(response.model_dump_json(indent=2))
    if response.status is ProviderStatus.FAILED:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
