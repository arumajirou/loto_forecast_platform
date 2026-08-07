from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from loto.data_access_ledger.canonical import canonical_json_bytes
from loto.data_access_ledger.contracts import DataAccessLedger
from loto.data_access_ledger.enums import (
    AccessDecision,
    FindingCode,
    FindingSeverity,
)
from loto.data_access_ledger.report import ValidationFinding, ValidationReport
from loto.data_access_ledger.validator import validate_ledger


def _write_report(path: Path | None, report: ValidationReport) -> None:
    payload = canonical_json_bytes(report)
    if path is None:
        sys.stdout.buffer.write(payload + b"\n")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload + b"\n")


def _invalid_report(message: str) -> ValidationReport:
    return ValidationReport(
        status=AccessDecision.INVALID,
        run_id="UNKNOWN",
        ledger_sha256="0" * 64,
        findings=[
            ValidationFinding(
                code=FindingCode.SCHEMA_VALIDATION_ERROR,
                severity=FindingSeverity.ERROR,
                message=message,
            )
        ],
        error_count=1,
        warning_count=0,
        verified_event_count=0,
    )


def _validate(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    report_path = Path(args.report) if args.report else None
    try:
        raw = ledger_path.read_bytes()
    except OSError as exc:
        print(f"ledger read error: {exc}", file=sys.stderr)
        return 2

    try:
        json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"ledger JSON error: {exc}", file=sys.stderr)
        return 2

    try:
        ledger = DataAccessLedger.model_validate_json(raw)
    except ValidationError as exc:
        report = _invalid_report(str(exc))
        try:
            _write_report(report_path, report)
        except OSError as write_exc:
            print(f"report write error: {write_exc}", file=sys.stderr)
            return 2
        return 1

    report = validate_ledger(ledger)
    try:
        _write_report(report_path, report)
    except OSError as exc:
        print(f"report write error: {exc}", file=sys.stderr)
        return 2
    return 0 if report.status is AccessDecision.PASS else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m loto.data_access_ledger.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate a Data Access Ledger JSON file")
    validate.add_argument("--ledger", required=True)
    validate.add_argument("--report")
    validate.set_defaults(handler=_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
