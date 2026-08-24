"""CLI for one deterministic exclusive-GPU forecast handoff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import SupervisorConfig
from .supervisor import ExclusiveGpuSupervisor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one exclusive GPU forecast handoff")
    parser.add_argument("--config", type=Path, required=True, help="JSON SupervisorConfig file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = SupervisorConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    result = ExclusiveGpuSupervisor(config).run()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
