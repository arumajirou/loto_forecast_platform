from __future__ import annotations

import argparse
from pathlib import Path

from loto.sktime_campaign.canary_evaluation import CanaryEvaluationRequest
from loto.sktime_campaign.canary_evaluation_artifacts import persist_p10


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    request = CanaryEvaluationRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    response = persist_p10(request)
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
