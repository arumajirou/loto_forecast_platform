#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from loto.coverage.instrumented import (
    run_auto_research_with_ledger,
    run_coverage_experiment_with_ledger,
)
from loto.coverage.ledger import CoverageLedgerError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run coverage build or bounded auto research with runtime Data Access "
            "Ledger evidence while keeping protected tests unopened."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "auto"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--config", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            result = run_coverage_experiment_with_ledger(args.config)
        else:
            result = run_auto_research_with_ledger(args.config)
    except (CoverageLedgerError, OSError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
