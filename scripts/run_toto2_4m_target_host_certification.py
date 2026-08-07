from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.toto2_campaign.certification_bundle import (  # noqa: E402
    build_artifact_manifest,
    create_deterministic_zip,
    expand_formal_matrix,
    load_json_object,
    sha256_file,
    validate_lock_review,
    validate_request_case,
    verify_artifact_manifest,
    write_sha256s,
)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_matrix(args: argparse.Namespace) -> tuple[Path, Path]:
    env_dir = ROOT / "environments" / "toto2-4m-py312"
    lock_path = env_dir / "uv.lock"
    review = validate_lock_review(args.lock_review, lock_path)
    cases = expand_formal_matrix(args.matrix_manifest, args.requests_root)
    for case in cases:
        validate_request_case(case)

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = args.output_root / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    matrix_results: list[dict[str, Any]] = []
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    for index, case in enumerate(cases, start=1):
        case_root = run_root / "cases" / case.case_id
        response_path = case_root / "response.json"
        command = [
            str(args.isolated_python),
            str(ROOT / "scripts" / "certify_toto2_4m_runtime.py"),
            "--request",
            str(case.request_path),
            "--response",
            str(response_path),
            "--snapshot",
            str(args.snapshot),
            "--isolated-python",
            str(args.isolated_python),
            "--run-dir",
            str(case_root / "runtime"),
            "--ready-timeout-seconds",
            str(args.ready_timeout_seconds),
            "--gpu-capture-timeout-seconds",
            str(args.gpu_capture_timeout_seconds),
        ]
        completed = subprocess.run(command, check=False, text=True)
        response = load_json_object(response_path) if response_path.exists() else {}
        result = {
            "index": index,
            "case_id": case.case_id,
            "request_path": str(case.request_path),
            "returncode": completed.returncode,
            "response_status": response.get("status"),
            "response_phase": response.get("phase"),
        }
        matrix_results.append(result)
        atomic_write_json(run_root / "MATRIX_PROGRESS.json", {"cases": matrix_results})
        if completed.returncode != 0 or response.get("status") != "OK":
            atomic_write_json(
                run_root / "MATRIX_RESULT.json",
                {
                    "status": "FAILED",
                    "failed_case": result,
                    "completed_cases": len(matrix_results),
                    "total_cases": len(cases),
                    "forecast_accuracy_certified": False,
                },
            )
            raise RuntimeError(f"formal matrix failed at {case.case_id}: {result}")

    finished_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    atomic_write_json(
        run_root / "MATRIX_RESULT.json",
        {
            "status": "PASS",
            "matrix_id": "toto2-4m-formal-v1",
            "started_at": started_at,
            "finished_at": finished_at,
            "total_cases": len(cases),
            "passed_cases": len(matrix_results),
            "two_process_replay_required_per_case": True,
            "lock_review": review,
            "runtime_certified": True,
            "forecast_accuracy_certified": False,
            "lottery_domain_compatibility_certified": False,
            "cases": matrix_results,
        },
    )

    excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    manifest = build_artifact_manifest(run_root, excluded_names=excluded)
    atomic_write_json(run_root / "ARTIFACT_MANIFEST.json", manifest)
    write_sha256s(run_root, manifest, run_root / "SHA256SUMS")
    verify_artifact_manifest(run_root, manifest)

    archive_path = run_root.with_suffix(".zip")
    archive_manifest = build_artifact_manifest(run_root)
    create_deterministic_zip(run_root, archive_path, archive_manifest)
    archive_sha_path = archive_path.with_suffix(".zip.sha256")
    archive_sha_path.write_text(
        f"{sha256_file(archive_path)}  {archive_path.name}\n",
        encoding="utf-8",
    )
    return run_root, archive_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run and package the Toto 2.0 4M target-host certification matrix"
    )
    parser.add_argument("--matrix-manifest", type=Path, required=True)
    parser.add_argument("--requests-root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--isolated-python", type=Path, required=True)
    parser.add_argument("--lock-review", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--ready-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--gpu-capture-timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    try:
        run_root, archive_path = run_matrix(args)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"TARGET_HOST_CERTIFICATION=FAILED\nERROR={type(exc).__name__}: {exc}")
        return 2
    print("TARGET_HOST_CERTIFICATION=PASS")
    print(f"RUN_ROOT={run_root}")
    print(f"ARCHIVE={archive_path}")
    print(f"ARCHIVE_SHA256={sha256_file(archive_path)}")
    print("FORECAST_ACCURACY_CERTIFIED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
