from __future__ import annotations

import argparse
import json
import shlex
from collections.abc import Sequence
from pathlib import Path

from .p6_campaign import run_p6_campaign
from .p6_contract import P6Status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the GluonTS P6 nine-model campaign")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--lane", choices=("compat", "latest"), required=True)
    parser.add_argument("--provider-command", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    campaign = run_p6_campaign(
        run_id=args.run_id,
        lane=args.lane,
        command=shlex.split(args.provider_command),
        artifact_root=args.artifact_root,
        workers=args.workers,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(campaign.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    if campaign.status is P6Status.VERIFIED:
        return 0
    if campaign.status is P6Status.BLOCKED:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
