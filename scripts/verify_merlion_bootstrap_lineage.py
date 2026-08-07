from __future__ import annotations

import argparse
from pathlib import Path

from loto.merlion_campaign.bootstrap_lineage import (
    file_sha256,
    read_json_object,
    validate_preflight_payload,
    validate_preflight_plan_lineage,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", required=True)
    parser.add_argument("--plan")
    parser.add_argument("--expected-report-sha256")
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()

    preflight_path = Path(args.preflight)
    preflight = read_json_object(preflight_path, label="PREFLIGHT.json")
    if args.plan:
        plan_path = Path(args.plan)
        plan = read_json_object(plan_path, label="BOOTSTRAP_PLAN.json")
        lineage = validate_preflight_plan_lineage(
            preflight,
            plan,
            require_attemptable=not args.allow_blocked,
        )
        report_sha256 = lineage["preflight_report_sha256"]
        print(f"BOOTSTRAP_PLAN_SHA256={lineage['plan_sha256']}")
    else:
        report_sha256 = validate_preflight_payload(
            preflight,
            require_attemptable=not args.allow_blocked,
            expected_report_sha256=args.expected_report_sha256,
        )

    if args.expected_report_sha256 and report_sha256 != args.expected_report_sha256:
        raise ValueError("preflight report SHA-256 does not match expected lineage")

    print("BOOTSTRAP_LINEAGE_STATUS=PASS")
    print(f"PREFLIGHT_REPORT_SHA256={report_sha256}")
    print(f"PREFLIGHT_FILE_SHA256={file_sha256(preflight_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
