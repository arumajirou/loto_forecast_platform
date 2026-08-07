from __future__ import annotations

import argparse
from pathlib import Path

from loto.merlion_campaign.dependency_gate import build_preflight_report, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-free-gib", type=float, default=5.0)
    args = parser.parse_args()
    root = args.root.resolve()
    report = build_preflight_report(
        root,
        root / "environments/merlion-core-py311",
        min_free_bytes=int(args.minimum_free_gib * 1024**3),
    )
    write_json(args.output, report)
    print(f"PREFLIGHT_STATUS={report['status']}")
    print(f"PREFLIGHT_CAN_ATTEMPT={str(report['can_attempt_bootstrap']).lower()}")
    print(f"PREFLIGHT_REPORT={args.output.resolve()}")
    return 0 if report["can_attempt_bootstrap"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
