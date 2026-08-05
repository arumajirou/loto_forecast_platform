from __future__ import annotations

import argparse
from pathlib import Path

from loto.statsforecast.runtime_lane_remediation import execute_bounded_remediation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute bounded StatsForecast runtime remediation."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--triage-dir", type=Path, required=True)
    parser.add_argument("--source-end-to-end-dir", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--prepare-offline", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args(argv)
    result = execute_bounded_remediation(
        args.repo_root,
        args.triage_dir,
        args.output_root,
        source_end_to_end_dir=args.source_end_to_end_dir,
        wheelhouse=args.wheelhouse,
        run_id=args.run_id,
        prepare_offline=args.prepare_offline,
        offline=args.offline,
        expected_commit=args.expected_commit,
        expected_seed=args.seed,
        horizon=args.horizon,
        max_attempts=args.max_attempts,
        uv_executable=args.uv,
    )
    print(f"REMEDIATION_DIR={result.output_dir}")
    print(f"REMEDIATION_REPORT={result.report_path}")
    print(f"REMEDIATION_ARCHIVE={result.archive_path}")
    print(f"REMEDIATION_ARCHIVE_SHA256={result.archive_sha256_path}")
    print(f"STATUS={result.status}")
    print(f"DECISION={result.decision}")
    return 0 if result.formal_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
