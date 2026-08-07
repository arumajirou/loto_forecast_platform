#!/usr/bin/env python3
"""Verify one completed database-backed NeuralForecast runtime campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.neuralforecast.db_runtime_verification import write_database_runtime_verification


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--expected-model-count", type=int)
    parser.add_argument("--require-gpu", action="store_true")
    parser.add_argument("--require-cpu", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.require_gpu and args.require_cpu:
        raise SystemExit("--require-gpu and --require-cpu are mutually exclusive")
    require_gpu = True if args.require_gpu else False if args.require_cpu else None
    report = write_database_runtime_verification(
        args.run_directory,
        expected_model_count=args.expected_model_count,
        require_gpu=require_gpu,
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
