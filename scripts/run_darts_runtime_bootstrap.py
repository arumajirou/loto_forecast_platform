#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_api() -> tuple[Any, Any]:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
    from loto.darts_campaign.runtime_bootstrap import (
        load_bootstrap_profile,
        run_runtime_bootstrap,
    )

    return load_bootstrap_profile, run_runtime_bootstrap


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve, sync, and certify an isolated Darts runtime.",
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_bootstrap_profile, run_runtime_bootstrap = _load_api()
    profile = load_bootstrap_profile(args.profile)
    report, approval = run_runtime_bootstrap(profile, args.repository_root)
    payload = {
        "report": report.model_dump(mode="json"),
        "approval": approval.model_dump(mode="json") if approval else None,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report.overall_status]


if __name__ == "__main__":
    raise SystemExit(main())
