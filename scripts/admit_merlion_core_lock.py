from __future__ import annotations

import argparse
from pathlib import Path

from loto.merlion_campaign.lock_admission import (
    atomic_write_text,
    evaluate_lock_admission,
    render_admission_decision,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence-zip", type=Path, required=True)
    parser.add_argument("--license-review", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_lock_admission(
        args.root,
        args.evidence_zip,
        args.license_review,
        expected_head=args.expected_head,
    )
    write_json(args.report, report)
    atomic_write_text(args.decision, render_admission_decision(report))
    print(f"LOCK_ADMISSION_STATUS={report['status']}")
    print(f"LOCK_ADMISSION_REPORT={args.report.resolve()}")
    print(f"LOCK_ADMISSION_DECISION={args.decision.resolve()}")
    return 0 if report["status"] == "ADMITTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
