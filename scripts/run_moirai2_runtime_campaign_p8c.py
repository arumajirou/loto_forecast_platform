from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.moirai2_campaign.runtime_evidence_gate import (  # noqa: E402
    sha256_file,
    write_sha256_manifest,
)
from loto.moirai2_campaign.runtime_source_identity import (  # noqa: E402
    capture_source_identity,
)

CAMPAIGN_RUNNER = ROOT / "scripts" / "run_moirai2_runtime_campaign.py"
PRINCIPAL_PATHS = (
    "scripts/run_moirai2_provider.py",
    "scripts/certify_moirai2_runtime.py",
    "scripts/run_moirai2_runtime_campaign.py",
    "scripts/run_moirai2_runtime_campaign_p8c.py",
    "scripts/verify_moirai2_runtime_evidence.py",
    "src/loto/adapters/moirai2/contracts.py",
    "src/loto/moirai2_campaign/covariates.py",
    "src/loto/moirai2_campaign/lock_review.py",
    "src/loto/moirai2_campaign/runtime_campaign.py",
    "src/loto/moirai2_campaign/runtime_certification.py",
    "src/loto/moirai2_campaign/runtime_evidence_gate.py",
    "src/loto/moirai2_campaign/runtime_evidence_common.py",
    "src/loto/moirai2_campaign/runtime_evidence_manifest.py",
    "src/loto/moirai2_campaign/runtime_evidence_prediction.py",
    "src/loto/moirai2_campaign/runtime_evidence_gpu.py",
    "src/loto/moirai2_campaign/runtime_evidence_case.py",
    "src/loto/moirai2_campaign/runtime_evidence_campaign.py",
    "src/loto/moirai2_campaign/runtime_evidence_pair.py",
    "src/loto/moirai2_campaign/runtime_preflight.py",
    "src/loto/moirai2_campaign/runtime_source_identity.py",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _artifact_manifest(output_dir: Path) -> dict[str, Any]:
    files = sorted(
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
        and path.name not in {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    )
    return {
        "schema_version": "moirai2-p8-runtime-campaign-artifacts-v1",
        "files": files,
        "file_count": len(files),
    }


def _seal_output(
    *,
    output_dir: Path,
    source_identity: dict[str, Any],
    command: list[str],
    return_code: int,
    started_ns: int,
    ended_ns: int,
    stdout: str,
    stderr: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "p8c_campaign.stdout.log"
    stderr_path = output_dir / "p8c_campaign.stderr.log"
    exit_path = output_dir / "p8c_campaign.exit_code.txt"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    exit_path.write_text(f"{return_code}\n", encoding="utf-8")
    config_path = output_dir / "campaign_config.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise RuntimeError("campaign_config.json is not an object")
        config["formal_entrypoint"] = (
            "scripts/run_moirai2_runtime_campaign_p8c.py"
        )
        config["source_identity"] = source_identity
        _write_json(config_path, config)
    launch_evidence = {
        "schema_version": "moirai2-p8c-launch-evidence-v1",
        "formal_entrypoint": "scripts/run_moirai2_runtime_campaign_p8c.py",
        "command": command,
        "return_code": return_code,
        "started_at_unix_ns": started_ns,
        "ended_at_unix_ns": ended_ns,
        "duration_seconds": (ended_ns - started_ns) / 1_000_000_000,
        "source_identity": source_identity,
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "exit_code_sha256": sha256_file(exit_path),
        "campaign_config_sha256": (
            sha256_file(config_path) if config_path.is_file() else None
        ),
    }
    _write_json(output_dir / "P8C_LAUNCH_EVIDENCE.json", launch_evidence)
    (output_dir / "SHA256SUMS").unlink(missing_ok=True)
    (output_dir / "ARTIFACT_MANIFEST.json").unlink(missing_ok=True)
    _write_json(
        output_dir / "ARTIFACT_MANIFEST.json",
        _artifact_manifest(output_dir),
    )
    write_sha256_manifest(output_dir, output_dir / "SHA256SUMS")


def _command(arguments: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(CAMPAIGN_RUNNER),
        "--campaign-id",
        arguments.campaign_id,
        "--snapshot-path",
        str(arguments.snapshot_path),
        "--runtime-lane",
        arguments.runtime_lane,
        "--device",
        arguments.device,
        "--output-dir",
        str(arguments.output_dir),
        "--history-length",
        str(arguments.history_length),
        "--context-length",
        str(arguments.context_length),
        "--prediction-length",
        str(arguments.prediction_length),
        "--timeout-seconds",
        str(arguments.timeout_seconds),
        "--monitor-interval-seconds",
        str(arguments.monitor_interval_seconds),
    ]
    for case_name in arguments.case or ():
        command.extend(["--case", case_name])
    if arguments.prepare_only:
        command.append("--prepare-only")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run and seal a Moirai 2.0 runtime campaign with clean-tree "
            "source identity"
        )
    )
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--snapshot-path", required=True, type=Path)
    parser.add_argument(
        "--runtime-lane",
        required=True,
        choices=("supported-py311", "cuda13-experimental"),
    )
    parser.add_argument("--device", required=True, choices=("cpu", "cuda"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--case", action="append")
    parser.add_argument("--history-length", type=int, default=128)
    parser.add_argument("--context-length", type=int, default=128)
    parser.add_argument(
        "--prediction-length",
        type=int,
        default=1,
        choices=(1, 2, 5),
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument(
        "--monitor-interval-seconds",
        type=float,
        default=0.25,
    )
    parser.add_argument("--prepare-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.output_dir.exists():
        raise SystemExit(f"output directory already exists: {arguments.output_dir}")
    source_identity = capture_source_identity(
        repo_root=ROOT,
        principal_paths=PRINCIPAL_PATHS,
    )
    command = _command(arguments)
    started_ns = time.time_ns()
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    ended_ns = time.time_ns()
    _seal_output(
        output_dir=arguments.output_dir,
        source_identity=source_identity,
        command=command,
        return_code=process.returncode,
        started_ns=started_ns,
        ended_ns=ended_ns,
        stdout=process.stdout,
        stderr=process.stderr,
    )
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
