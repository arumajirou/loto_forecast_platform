"""CLI for AutoSegRNN source fingerprinting and runtime certification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runtime_certification import (
    AutoSegRNNCertificationError,
    RuntimeSDKUnavailableError,
    certify_auto_segrnn,
)
from .runtime_contracts import load_runtime_request
from .runtime_source import (
    SourceIdentityError,
    canonical_source_tree_sha256,
    collect_source_inventory,
    verify_git_checkout,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fingerprint = subparsers.add_parser("fingerprint")
    fingerprint.add_argument("--working-directory", type=Path, required=True)
    fingerprint.add_argument("--source-revision", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    return parser


def _fingerprint(working_directory: Path, source_revision: str) -> int:
    verify_git_checkout(working_directory, source_revision)
    files = collect_source_inventory(working_directory)
    payload = {
        "source_revision": source_revision,
        "source_tree_sha256": canonical_source_tree_sha256(files),
        "files": [item.model_dump(mode="json") for item in files],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run(request_path: Path, output_root: Path) -> int:
    request = load_runtime_request(request_path)
    report = certify_auto_segrnn(request, output_root)
    print(
        json.dumps(
            {
                "status": report.runtime_status.value,
                "certification_id": report.certification_id,
                "accuracy_status": report.accuracy_status.value,
                "output_root": str(output_root.resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fingerprint":
            return _fingerprint(args.working_directory, args.source_revision)
        return _run(args.request, args.output_root)
    except (
        OSError,
        ValueError,
        RuntimeSDKUnavailableError,
        AutoSegRNNCertificationError,
        SourceIdentityError,
        RuntimeError,
    ) as exc:
        payload = {
            "status": "BLOCKED",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
