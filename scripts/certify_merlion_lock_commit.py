from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from loto.merlion_campaign.bootstrap_evidence_verify import verify_bootstrap_evidence_zip
from loto.merlion_campaign.license_review import (
    parse_dependency_inventory,
    validate_license_review,
)
from loto.merlion_campaign.lock_admission import read_evidence_payloads
from loto.merlion_campaign.lock_commit import (
    evaluate_lock_commit,
    render_lock_commit_decision,
    validate_lock_commit_report,
    write_json,
)


def _license_validator(
    review: Mapping[str, Any],
    inventory_data: bytes,
    evidence_zip_sha256: str,
    lock_sha256: str,
) -> list[str]:
    rows = parse_dependency_inventory(inventory_data)
    blockers, _ = validate_license_review(
        review,
        rows,
        evidence_zip_sha256=evidence_zip_sha256,
        lock_sha256=lock_sha256,
    )
    return blockers


def _run(args: argparse.Namespace) -> int:
    report = evaluate_lock_commit(
        args.root,
        args.admission_report,
        args.evidence_zip,
        args.license_review,
        expected_head=args.expected_head,
        evidence_verifier=verify_bootstrap_evidence_zip,
        evidence_payload_reader=read_evidence_payloads,
        license_validator=_license_validator,
    )
    write_json(args.report, report)
    args.decision.write_text(render_lock_commit_decision(report), encoding="utf-8")
    print(f"LOCK_COMMIT_STATUS={report['status']}")
    print(f"LOCK_COMMIT_REPORT={args.report.resolve()}")
    print(f"LOCK_COMMIT_DECISION={args.decision.resolve()}")
    return 0 if report["status"] == "LOCK_COMMIT_CERTIFIED" else 2


def _verify(args: argparse.Namespace) -> int:
    payload = json.loads(args.report.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("lock commit report must be a JSON object")
    blockers = validate_lock_commit_report(
        args.root,
        payload,
        expected_head=args.expected_head,
    )
    status = "PASS" if not blockers else "BLOCKED"
    print(f"LOCK_COMMIT_REPORT_VERIFY={status}")
    for blocker in blockers:
        print(f"LOCK_COMMIT_REPORT_BLOCKER={blocker}")
    return 0 if not blockers else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--root", type=Path, required=True)
    run_parser.add_argument("--admission-report", type=Path, required=True)
    run_parser.add_argument("--evidence-zip", type=Path, required=True)
    run_parser.add_argument("--license-review", type=Path, required=True)
    run_parser.add_argument("--expected-head", required=True)
    run_parser.add_argument("--report", type=Path, required=True)
    run_parser.add_argument("--decision", type=Path, required=True)
    run_parser.set_defaults(handler=_run)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--report", type=Path, required=True)
    verify_parser.add_argument("--expected-head", required=True)
    verify_parser.set_defaults(handler=_verify)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
