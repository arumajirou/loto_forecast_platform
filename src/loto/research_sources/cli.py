from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from .registry import load_registry, validation_report


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Research Source Registry v1")
    parser.add_argument("registry", type=Path)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        registry = load_registry(args.registry)
        report = validation_report(registry)
        if args.report is not None:
            _atomic_write_json(args.report, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, ValidationError) as exc:
        report = {
            "status": "INVALID",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "runtime_success": False,
            "production_eligibility": False,
        }
        if args.report is not None:
            _atomic_write_json(args.report, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
