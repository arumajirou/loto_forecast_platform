"""CLI for AutoFreTS source fingerprinting and runtime certification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .runtime_certification import certify_auto_frets
from .runtime_contracts import load_runtime_request
from .runtime_source import (
    canonical_source_tree_sha256,
    collect_source_inventory,
    verify_git_checkout,
)


def _json_dump(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )


def fingerprint(
    working_directory: Path,
    source_revision: str,
) -> dict[str, Any]:
    verify_git_checkout(
        working_directory,
        source_revision,
    )
    files = collect_source_inventory(working_directory)
    return {
        "schema_version": "1.0.0",
        "model_id": "nf-local-auto-frets",
        "source_revision": source_revision,
        "source_tree_sha256": canonical_source_tree_sha256(files),
        "files": [
            item.model_dump(mode="json")
            for item in files
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    fingerprint_parser = subparsers.add_parser(
        "fingerprint",
        help="fingerprint a clean AutoFreTS source checkout",
    )
    fingerprint_parser.add_argument(
        "--working-directory",
        type=Path,
        required=True,
    )
    fingerprint_parser.add_argument(
        "--source-revision",
        required=True,
    )

    run_parser = subparsers.add_parser(
        "run",
        help="run AutoFreTS runtime certification",
    )
    run_parser.add_argument(
        "--request",
        type=Path,
        required=True,
    )
    run_parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fingerprint":
        _json_dump(
            fingerprint(
                args.working_directory,
                args.source_revision,
            )
        )
        return 0

    request = load_runtime_request(args.request)
    report = certify_auto_frets(
        request,
        args.output_root,
    )
    _json_dump(report.model_dump(mode="json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
