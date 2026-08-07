#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.darts_campaign.protocol import DartsRequest
from loto.darts_campaign.provider import run_request, write_response


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run isolated Darts provider request")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--data", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    request = DartsRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    frame = None
    if args.data is not None:
        if args.data.suffix == ".parquet":
            frame = pd.read_parquet(args.data)
        else:
            frame = pd.read_csv(args.data)
    write_response(run_request(request, frame=frame), args.response)


if __name__ == "__main__":
    main()
