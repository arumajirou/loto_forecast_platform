"""CLI for AutoTimeLLM target-host runtime certification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runtime_certification import (
    AutoTimeLLMCertificationError,
    RuntimeSDKUnavailableError,
    certify_auto_timellm,
)
from .runtime_contracts import load_runtime_request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = load_runtime_request(args.request)
        report = certify_auto_timellm(request, args.output_root)
    except (
        OSError,
        ValueError,
        RuntimeSDKUnavailableError,
        AutoTimeLLMCertificationError,
        RuntimeError,
    ) as exc:
        payload = {
            "status": "BLOCKED",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": report.runtime_status.value,
                "certification_id": report.certification_id,
                "accuracy_status": report.accuracy_status.value,
                "output_root": str(args.output_root.resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
