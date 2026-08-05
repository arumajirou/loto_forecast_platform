from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from loto.statsforecast.runtime_lane import (
    execute_runtime_lane,
    fetch_release_artifact,
    prepare_offline_bundle,
    run_target_host_certification,
    verify_target_host_package,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision and run StatsForecast 2.1.1.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch-release")
    fetch_parser.add_argument("--wheelhouse", type=Path, required=True)

    prepare_parser = subparsers.add_parser("prepare-offline")
    prepare_parser.add_argument("--wheelhouse", type=Path, required=True)
    prepare_parser.add_argument("--uv", default="uv")

    run_parser = subparsers.add_parser("certify")
    run_parser.add_argument("--output-root", type=Path, required=True)
    run_parser.add_argument("--run-id")
    run_parser.add_argument("--wheelhouse", type=Path)
    run_parser.add_argument("--offline", action="store_true")
    run_parser.add_argument("--uv", default="uv")
    run_parser.add_argument("--horizon", type=int, default=1)
    run_parser.add_argument("--seed", type=int, default=1)

    target_parser = subparsers.add_parser("target-host")
    target_parser.add_argument("--output-root", type=Path, required=True)
    target_parser.add_argument("--run-id")
    target_parser.add_argument("--wheelhouse", type=Path)
    target_parser.add_argument("--prepare-offline", action="store_true")
    target_parser.add_argument("--offline", action="store_true")
    target_parser.add_argument("--uv", default="uv")
    target_parser.add_argument("--horizon", type=int, default=1)
    target_parser.add_argument("--seed", type=int, default=1)

    verify_parser = subparsers.add_parser("verify-package")
    verify_parser.add_argument("--archive", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.command == "verify-package":
        report = verify_target_host_package(args.archive)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["status"] == "PASS" else 2
    if args.command == "target-host":
        result = run_target_host_certification(
            _repo_root(),
            args.output_root,
            run_id=args.run_id,
            wheelhouse=args.wheelhouse,
            prepare_offline=args.prepare_offline,
            offline=args.offline,
            uv_executable=args.uv,
            horizon=args.horizon,
            seed=args.seed,
        )
        print(f"CONTROLLER_DIR={result.controller_dir}")
        print(f"ARCHIVE={result.archive_path}")
        print(f"ARCHIVE_SHA256={result.archive_sha256_path}")
        print(f"STATUS={result.status}")
        return 0 if result.status == "PASS" else 2

    if args.command == "fetch-release":
        artifact = fetch_release_artifact(args.wheelhouse)
        print(f"ARTIFACT={artifact}")
        return 0
    if args.command == "prepare-offline":
        bundle = prepare_offline_bundle(
            _repo_root(),
            args.wheelhouse,
            uv_executable=args.uv,
        )
        print(f"WHEELHOUSE={bundle}")
        return 0

    run_id = args.run_id or datetime.now(timezone.utc).strftime(
        "statsforecast-lane-%Y%m%d-%H%M%S"
    )
    run_dir = execute_runtime_lane(
        _repo_root(),
        args.output_root,
        run_id=run_id,
        wheelhouse=args.wheelhouse,
        offline=args.offline,
        uv_executable=args.uv,
        horizon=args.horizon,
        seed=args.seed,
    )
    report = json.loads((run_dir / "RUNTIME_LANE_REPORT.json").read_text(encoding="utf-8"))
    print(f"RUN_DIR={run_dir}")
    print(f"STATUS={report['status']}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
