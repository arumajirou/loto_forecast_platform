#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_api() -> tuple[Any, Any, Any]:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
    from loto.darts_campaign.runtime_preflight import (
        load_profile,
        run_runtime_preflight,
        write_report,
    )

    return load_profile, run_runtime_preflight, write_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fail-closed Darts runtime preflight checks.",
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_profile, run_runtime_preflight, write_report = _load_api()
    profile = load_profile(args.profile)
    report = run_runtime_preflight(profile, args.repository_root)
    write_report(report, args.output)
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report.overall_status]


if __name__ == "__main__":
    raise SystemExit(main())
