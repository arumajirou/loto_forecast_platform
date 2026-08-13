from __future__ import annotations

import argparse
import json
from pathlib import Path

from .inventory import discover_estimators
from .runner import certify_all, certify_estimator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loto-sklearn")
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("list", help="list estimators discovered from installed scikit-learn")
    inventory.add_argument(
        "--kind",
        choices=("all", "classifier", "regressor", "cluster", "transformer", "other"),
        default="all",
    )
    inventory.add_argument("--json", action="store_true")

    smoke = sub.add_parser("smoke", help="fit and exercise one estimator")
    smoke.add_argument("--model", required=True)
    smoke.add_argument("--seed", type=int, default=1)

    certify = sub.add_parser("certify", help="fit and exercise all discovered estimators")
    certify.add_argument(
        "--kind",
        choices=("all", "classifier", "regressor", "cluster", "transformer", "other"),
        default="all",
    )
    certify.add_argument("--seed", type=int, default=1)
    certify.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "list":
        records = discover_estimators(args.kind)
        if args.json:
            print(json.dumps([record.to_dict() for record in records], indent=2, sort_keys=True))
        else:
            for record in records:
                print(f"{record.kind:11s} {record.name} ({record.module})")
            print(f"TOTAL={len(records)}")
        return 0
    if args.command == "smoke":
        result = certify_estimator(args.model, seed=args.seed)
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0 if result.status == "VERIFIED" else 1
    report = certify_all(seed=args.seed, kind=args.kind, output_dir=args.output)
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
