from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.matrix_verification import finalize_p1_run
from loto.sktime_campaign.verification import VerificationError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify and finalize a sktime P1 matrix certification run."
    )
    parser.add_argument("--run", required=True, help="P1 run directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = finalize_p1_run(Path(args.run))
    except (OSError, VerificationError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
