from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loto.statsforecast.runtime_lane_operator import run_target_host_operator


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the hardened StatsForecast target-host operator."
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--prepare-offline", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--tts", action="store_true")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--hold-open", action="store_true")
    args = parser.parse_args(argv)

    result = run_target_host_operator(
        _repo_root(),
        args.output_root,
        wheelhouse=args.wheelhouse,
        run_id=args.run_id,
        prepare_offline=args.prepare_offline,
        offline=args.offline,
        expected_commit=args.expected_commit,
        expected_seed=args.seed,
        horizon=args.horizon,
        uv_executable=args.uv,
        enable_tts=args.tts,
        enable_email=args.email,
    )
    print(f"OPERATOR_DIR={result.output_dir}")
    print(f"OPERATOR_REPORT={result.report_path}")
    print(f"NOTIFICATION_REPORT={result.notification_report_path}")
    print(f"DECISION={result.decision}")

    exit_code = 0 if result.formal_pass else 2
    if args.hold_open and sys.stdin.isatty():
        input("Press Enter to close this terminal...")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
