from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_sktime_p5_lock import load_context, load_request
from loto.sktime_campaign.prospective_artifacts import verify_prospective_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a sktime P5 Prospective shadow-lock bundle."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--p4-artifact-sha256", required=True)
    parser.add_argument("--p4-selected-candidate", required=True)
    parser.add_argument("--p4-response-sha256", required=True)
    parser.add_argument("--p4-sha256sums-sha256", required=True)
    parser.add_argument("--p4-aggregates-sha256", required=True)
    parser.add_argument("--allow-nonpass", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = verify_prospective_bundle(
        Path(args.output),
        load_request(args),
        load_context(args),
        formal=not args.allow_nonpass,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
