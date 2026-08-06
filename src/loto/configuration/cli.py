"""Command-line validation for the strict configuration foundation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .loader import load_config, write_resolved_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loto-strict-config")
    parser.add_argument("config", help="versioned YAML configuration")
    parser.add_argument("--resolved-output", default=None)
    parser.add_argument("--ignore-environment", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    environment = {} if args.ignore_environment else os.environ
    try:
        resolved = load_config(args.config, environ=environment)
        output_path: Path | None = None
        sidecar_path: Path | None = None
        if args.resolved_output:
            output_path, sidecar_path = write_resolved_config(resolved, args.resolved_output)
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "INVALID", "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "VALID",
                "config_schema_version": resolved.config.config_schema_version,
                "resolved_config_sha256": resolved.config_sha256,
                "environment_override_count": len(resolved.overrides),
                "resolved_output": str(output_path) if output_path else None,
                "sha256_sidecar": str(sidecar_path) if sidecar_path else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
