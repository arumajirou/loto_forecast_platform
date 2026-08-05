#!/usr/bin/env python3
"""Run the formal promotion gate after validating the locked dependency contract."""

from __future__ import annotations

import json

from hierarchicalforecast_target.dependency_contract import verify_dependency_contract
from hierarchicalforecast_target.promotion_gate import main as promotion_main
from hierarchicalforecast_target.promotion_gate import parser as promotion_parser


def main(argv: list[str] | None = None) -> int:
    args = promotion_parser().parse_args(argv)
    try:
        verify_dependency_contract(args.repo_root)
    except Exception as exc:
        report = {
            "status": "FAILED_DEPENDENCY_CONTRACT_PREFLIGHT",
            "formal_success": False,
            "ready_for_review": False,
            "ci_required": True,
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 3
    return promotion_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
