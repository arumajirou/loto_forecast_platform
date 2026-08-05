from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.merlion_campaign.bootstrap_resume import build_resume_plan, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--managed-python-dir", type=Path)
    args = parser.parse_args()
    preflight = json.loads(args.preflight.read_text(encoding="utf-8"))
    plan = build_resume_plan(
        preflight,
        args.root,
        run_id=args.run_id,
        managed_python_dir=args.managed_python_dir,
    )
    write_json(args.output, plan)
    print(f"BOOTSTRAP_PLAN_STATUS={plan['status']}")
    print(f"BOOTSTRAP_PLAN_STRATEGY={plan['strategy']}")
    print(f"BOOTSTRAP_PLAN={args.output.resolve()}")
    return 0 if plan["status"] != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
