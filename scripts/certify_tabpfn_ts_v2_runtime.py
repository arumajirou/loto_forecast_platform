from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from loto.adapters.tabpfn_ts.runtime_certifier import (
    RuntimeCertificationConfig,
    RuntimeCertificationError,
    certify_runtime,
    write_json_atomic,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify TabPFN-TS V2 in separate processes")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--provider-python", required=True, type=Path)
    parser.add_argument(
        "--provider-script",
        type=Path,
        default=Path("scripts/run_tabpfn_ts_v2_certified_provider.py"),
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--repository-cache-root", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/tabpfn-ts-v2-runtime"))
    parser.add_argument("--run-id")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--hold-seconds", type=float, default=3.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.1)
    parser.add_argument("--process-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--prediction-tolerance", type=float, default=0.0)
    parser.add_argument("--nvidia-smi-command", default="nvidia-smi")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    run_id = args.run_id or datetime.now(UTC).strftime("tabpfn-v2-%Y%m%dT%H%M%SZ")
    config = RuntimeCertificationConfig(
        run_id=run_id,
        repo_root=repo_root,
        provider_python=args.provider_python.resolve(),
        provider_script=(
            args.provider_script.resolve()
            if args.provider_script.is_absolute()
            else (repo_root / args.provider_script).resolve()
        ),
        request_path=args.request.resolve(),
        snapshot_path=args.snapshot.resolve(),
        repository_cache_root=args.repository_cache_root.resolve(),
        output_root=(
            args.output_root.resolve()
            if args.output_root.is_absolute()
            else (repo_root / args.output_root).resolve()
        ),
        device=args.device,
        seed=args.seed,
        repeats=args.repeats,
        hold_seconds=args.hold_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        process_timeout_seconds=args.process_timeout_seconds,
        prediction_tolerance=args.prediction_tolerance,
        nvidia_smi_command=args.nvidia_smi_command,
        license_accepted=True,
    )
    try:
        report = certify_runtime(config)
    except Exception as exc:
        output_dir = config.output_root / config.run_id
        failure = {
            "schema_version": 1,
            "run_id": config.run_id,
            "status": "FAIL",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "error_type": type(exc).__name__,
            "failure_reason": str(exc),
        }
        write_json_atomic(output_dir / "runtime-certification-failure.json", failure)
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
        return 2 if isinstance(exc, RuntimeCertificationError) else 1
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
