from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.mlforecast.runner import run_from_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loto-mlforecast",
        description="Leakage-safe MLForecast and AutoMLForecast execution",
    )
    parser.add_argument("--data", type=Path, required=True, help="CSV or Parquet input panel")
    parser.add_argument("--config", type=Path, required=True, help="YAML execution config")
    parser.add_argument(
        "--prospective-exogenous",
        type=Path,
        default=None,
        help="Optional CSV/Parquet future exogenous rows for prospective prediction",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_from_paths(args.data, args.config, args.prospective_exogenous)
    print(
        json.dumps(
            {
                "status": result.status,
                "run_id": result.run_id,
                "run_dir": str(result.run_dir),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
