from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.time_series_library_campaign import execute_request_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated TSLib provider contract")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    return execute_request_file(args.request, args.response)


if __name__ == "__main__":
    raise SystemExit(main())
