#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.orchestration.pipeline_staged import run_trusted_vertical_slice_staged


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def parse_windows(value: str) -> tuple[int, ...]:
    try:
        windows = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("windows must be comma-separated integers") from exc
    if not windows or any(window < 1 for window in windows):
        raise argparse.ArgumentTypeError("windows must contain positive integers")
    return windows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the trusted vertical slice through Data Access Ledger validation "
            "without Registry, MLflow, release, or ArtifactStore commits."
        )
    )
    parser.add_argument("--input", required=True, help="Canonical-compatible Loto7 CSV")
    parser.add_argument("--output", required=True, help="New empty output directory")
    parser.add_argument("--backtest-draws", type=positive_int, default=20)
    parser.add_argument("--windows", type=parse_windows, default=(10, 30, 100))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--secret-env",
        default="LOTO_FORECAST_SEAL_SECRET",
        help="Environment variable containing the local forecast-seal secret",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    secret_text = os.environ.get(args.secret_env)
    if secret_text is None:
        print(f"missing required secret environment variable: {args.secret_env}", file=sys.stderr)
        return 2
    try:
        result = run_trusted_vertical_slice_staged(
            args.input,
            args.output,
            secret=secret_text.encode("utf-8"),
            backtest_draws=args.backtest_draws,
            windows=args.windows,
            seed=args.seed,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
