from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_sktime_p5_monitor import load_request

from loto.sktime_campaign.prospective_artifacts import (
    verify_prospective_monitor,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a sktime P5 Prospective monitoring bundle."
    )
    parser.add_argument("--actuals-config", required=True)
    parser.add_argument("--prediction-lock", required=True)
    parser.add_argument("--holdout-reference-metrics", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--revealed-at-utc")
    parser.add_argument("--allow-nonpass", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = verify_prospective_monitor(
        Path(args.output),
        load_request(args),
        formal=not args.allow_nonpass,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
