from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.holdout_artifacts import (
    P4VerificationError,
    verify_p4,
)
from run_sktime_p4_holdout_score import load_inputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a sktime P4 sealed Holdout score bundle."
    )
    parser.add_argument("--actuals-config", required=True)
    parser.add_argument("--prediction-lock", required=True)
    parser.add_argument("--p3-sha256sums", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--revealed-at-utc", required=True)
    parser.add_argument("--scored-at-utc", required=True)
    parser.add_argument("--allow-nonpass", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request, lock = load_inputs(args)
    try:
        report = verify_p4(
            Path(args.output),
            request,
            lock,
            formal=not args.allow_nonpass,
        )
    except (OSError, ValueError, P4VerificationError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
