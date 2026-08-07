from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .p7d_bundle import (
    P7DBundleError,
    create_evidence_bundle,
    verify_and_extract_bundle,
    verify_evidence_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export or verify a GluonTS P7D evidence handoff ZIP"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export")
    export.add_argument("--run-root", type=Path, required=True)
    export.add_argument("--archive", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "export":
            manifest, archive_sha = create_evidence_bundle(
                args.run_root,
                args.archive,
            )
            payload = {
                "phase": manifest.phase,
                "operation": "export",
                "run_id": manifest.run_id,
                "archive": str(args.archive.resolve()),
                "archive_sha256": archive_sha,
                "entry_count": len(manifest.entries),
                "p8_eligible": manifest.p8_eligible,
            }
        else:
            if args.output_dir is None:
                report = verify_evidence_bundle(args.archive)
                output_dir = None
            else:
                report = verify_and_extract_bundle(
                    args.archive,
                    args.output_dir,
                )
                output_dir = str(args.output_dir.resolve())
            payload = {
                **report.model_dump(mode="json"),
                "operation": "verify",
                "output_dir": output_dir,
            }
    except (P7DBundleError, ValueError, FileNotFoundError) as exc:
        print(
            f"P7D_FAILED={type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
