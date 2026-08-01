#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from loto.models.catalog import list_model_specs
from loto.validation.argument_matrix import build_argument_inventory, build_smoke_cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an auditable all-model/all-argument lifecycle smoke matrix."
    )
    parser.add_argument("--models", default="all", help="all or comma-separated model IDs")
    parser.add_argument("--available-only", action="store_true")
    parser.add_argument("--profile", choices=("quick", "oat"), default="quick")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    specs = list(list_model_specs(available_only=args.available_only))
    if args.models != "all":
        requested = {item.strip() for item in args.models.split(",") if item.strip()}
        known = {spec.model_id for spec in specs}
        missing = sorted(requested - known)
        if missing:
            raise SystemExit(f"unknown models: {missing}")
        specs = [spec for spec in specs if spec.model_id in requested]

    inventory = build_argument_inventory(specs)
    cases = build_smoke_cases(specs, inventory, profile=args.profile)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    inventory_rows = [row.to_dict() for row in inventory]
    case_rows = []
    for case in cases:
        row = case.to_dict()
        row["requested_params"] = json.dumps(
            row["requested_params"], ensure_ascii=False, default=str
        )
        row["expected_checks"] = json.dumps(row["expected_checks"], ensure_ascii=False)
        case_rows.append(row)
    write_csv(args.output_dir / "model_argument_inventory.csv", inventory_rows)
    write_csv(args.output_dir / "lifecycle_smoke_cases.csv", case_rows)
    (args.output_dir / "lifecycle_smoke_cases.json").write_text(
        json.dumps([case.to_dict() for case in cases], indent=2, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
    )

    source_counts = Counter(row.source for row in inventory)
    manifest = {
        "schema_version": "1.0",
        "profile": args.profile,
        "model_count": len(specs),
        "argument_row_count": len(inventory),
        "smoke_case_count": len(cases),
        "smoke_eligible_argument_rows": sum(row.smoke_eligible for row in inventory),
        "source_counts": dict(source_counts),
        "coverage_definition": {
            "quick": "one maximal-safe lifecycle case per model",
            "oat": (
                "quick plus one-at-a-time mutation for every argument with a bounded smoke value"
            ),
            "excluded": (
                "Cartesian combinations and unsafe/unbounded "
                "domains are inventoried but not auto-mutated"
            ),
        },
        "required_lifecycle_checks": [
            "fit",
            "predict",
            "save",
            "load",
            "reload_predict",
            "property_reflection",
            "argument_verification",
            "retrain",
            "retrain_predict",
            "artifact_hash",
        ],
    }
    (args.output_dir / "audit_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
