from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.adapters.moirai2.contracts import Moirai2ProviderRequest  # noqa: E402
from loto.moirai2_campaign.runtime_campaign import (  # noqa: E402
    FORMAL_CASE_NAMES,
    RuntimeCampaignError,
    build_campaign_requests,
    sha256_file,
    summarize_campaign,
    validate_generated_request,
    write_sha256_manifest,
)
from loto.moirai2_campaign.runtime_preflight import (  # noqa: E402
    run_frozen_probe,
    validate_lane_files,
)

CERTIFIER = ROOT / "scripts" / "certify_moirai2_runtime.py"
RUNTIME_LANES = {
    "supported-py311": ROOT / "environments" / "moirai2-supported-py311",
    "cuda13-experimental": ROOT / "environments" / "moirai2-cuda13-experimental",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _run_case(
    *,
    case_name: str,
    request_path: Path,
    runtime_lane: str,
    output_dir: Path,
    timeout_seconds: int,
    monitor_interval_seconds: float,
) -> dict[str, Any]:
    case_dir = output_dir / "cases" / case_name
    command = [
        sys.executable,
        str(CERTIFIER),
        "--request",
        str(request_path),
        "--runtime-lane",
        runtime_lane,
        "--output-dir",
        str(case_dir),
        "--timeout-seconds",
        str(timeout_seconds),
        "--monitor-interval-seconds",
        str(monitor_interval_seconds),
    ]
    timed_out = False
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=(timeout_seconds * 2) + 120,
            check=False,
        )
        stdout = process.stdout
        stderr = process.stderr
        return_code = process.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return_code = 124
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "campaign_launcher.stdout.log").write_text(
        stdout,
        encoding="utf-8",
    )
    (case_dir / "campaign_launcher.stderr.log").write_text(
        stderr,
        encoding="utf-8",
    )
    (case_dir / "campaign_launcher.exit_code.txt").write_text(
        f"{return_code}\n",
        encoding="utf-8",
    )
    certification_path = case_dir / "certification.json"
    certification: dict[str, Any] | None = None
    if certification_path.is_file():
        certification = json.loads(certification_path.read_text(encoding="utf-8"))
    status = (
        "PASS"
        if return_code == 0
        and certification is not None
        and certification.get("status") == "PASS"
        else "FAILED"
    )
    result = {
        "case": case_name,
        "status": status,
        "message": (
            "two-process certification passed"
            if status == "PASS"
            else "two-process certification failed"
        ),
        "request_path": str(request_path.relative_to(output_dir)),
        "request_sha256": sha256_file(request_path),
        "certification_path": (
            str(certification_path.relative_to(output_dir))
            if certification_path.is_file()
            else None
        ),
        "launcher_return_code": return_code,
        "launcher_timed_out": timed_out,
        "certification": certification,
    }
    _write_json(case_dir / "campaign_case_result.json", result)
    return result


def _artifact_manifest(output_dir: Path) -> dict[str, Any]:
    files = sorted(
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    )
    return {
        "schema_version": "moirai2-p8-runtime-campaign-artifacts-v1",
        "files": files,
        "file_count": len(files),
    }


def run_campaign(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.runtime_lane not in RUNTIME_LANES:
        raise RuntimeCampaignError(
            f"unsupported runtime lane: {arguments.runtime_lane}"
        )
    if (
        arguments.device == "cuda"
        and arguments.runtime_lane != "cuda13-experimental"
    ):
        raise RuntimeCampaignError(
            "CUDA campaign requires cuda13-experimental lane"
        )
    if (
        arguments.monitor_interval_seconds <= 0
        or arguments.monitor_interval_seconds > 5
    ):
        raise RuntimeCampaignError(
            "monitor interval must be in the range (0, 5]"
        )
    if not CERTIFIER.is_file():
        raise RuntimeCampaignError(f"P8 certifier is missing: {CERTIFIER}")

    output_dir = arguments.output_dir
    output_dir.mkdir(parents=True, exist_ok=False)
    selected_cases = tuple(arguments.case or FORMAL_CASE_NAMES)
    if len(selected_cases) != len(set(selected_cases)):
        raise RuntimeCampaignError(
            "selected certification cases must be unique"
        )
    campaign_config = {
        "schema_version": "moirai2-p8-runtime-campaign-v1",
        "campaign_id": arguments.campaign_id,
        "runtime_lane": arguments.runtime_lane,
        "device": arguments.device,
        "snapshot_path": str(arguments.snapshot_path.resolve()),
        "selected_cases": list(selected_cases),
        "execution_policy": "strictly_serial",
        "parallel_case_count": 1,
        "history_length": arguments.history_length,
        "context_length": arguments.context_length,
        "prediction_length": arguments.prediction_length,
        "timeout_seconds": arguments.timeout_seconds,
        "monitor_interval_seconds": arguments.monitor_interval_seconds,
        "prepare_only": arguments.prepare_only,
        "seed": 1,
    }
    _write_json(output_dir / "campaign_config.json", campaign_config)

    lane_evidence = validate_lane_files(
        RUNTIME_LANES[arguments.runtime_lane],
        arguments.snapshot_path,
        runtime_lane=arguments.runtime_lane,
    )
    probe = run_frozen_probe(
        environment_path=RUNTIME_LANES[arguments.runtime_lane],
        requested_device=arguments.device,
        timeout_seconds=min(arguments.timeout_seconds, 600),
    )
    preflight = {
        "status": "PASS",
        "phase": "P8_RUNTIME_PREFLIGHT",
        "runtime_lane": arguments.runtime_lane,
        "requested_device": arguments.device,
        "lane_evidence": lane_evidence,
        "probe": probe,
    }
    _write_json(output_dir / "preflight.json", preflight)

    request_payloads = build_campaign_requests(
        campaign_id=arguments.campaign_id,
        snapshot_path=arguments.snapshot_path,
        device=arguments.device,
        selected_cases=selected_cases,
        history_length=arguments.history_length,
        context_length=arguments.context_length,
        prediction_length=arguments.prediction_length,
    )
    request_paths: dict[str, Path] = {}
    for case_name, payload in request_payloads.items():
        validate_generated_request(case_name, payload)
        validated = Moirai2ProviderRequest.model_validate(payload)
        request_path = output_dir / "requests" / f"{case_name}.json"
        _write_json(request_path, validated.model_dump(mode="json"))
        request_paths[case_name] = request_path

    if arguments.prepare_only:
        summary = {
            "schema_version": "moirai2-p8-runtime-campaign-v1",
            "status": "PREPARED",
            "phase": "P8_RUNTIME_CAMPAIGN",
            "campaign_id": arguments.campaign_id,
            "selected_cases": list(request_paths),
            "formal_runtime_certified": False,
            "message": (
                "preflight and request generation passed; "
                "inference was not run"
            ),
        }
    else:
        case_results = [
            _run_case(
                case_name=case_name,
                request_path=request_paths[case_name],
                runtime_lane=arguments.runtime_lane,
                output_dir=output_dir,
                timeout_seconds=arguments.timeout_seconds,
                monitor_interval_seconds=arguments.monitor_interval_seconds,
            )
            for case_name in request_paths
        ]
        summary = summarize_campaign(
            case_results=case_results,
            required_cases=request_paths,
            runtime_lane=arguments.runtime_lane,
            requested_device=arguments.device,
        )
        summary["campaign_id"] = arguments.campaign_id
        summary["preflight_status"] = "PASS"
    _write_json(output_dir / "campaign_summary.json", summary)
    _write_json(
        output_dir / "ARTIFACT_MANIFEST.json",
        _artifact_manifest(output_dir),
    )
    write_sha256_manifest(output_dir, output_dir / "SHA256SUMS")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the six-case Moirai 2.0 target-host "
            "certification campaign"
        )
    )
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--snapshot-path", required=True, type=Path)
    parser.add_argument(
        "--runtime-lane",
        required=True,
        choices=sorted(RUNTIME_LANES),
    )
    parser.add_argument("--device", required=True, choices=("cpu", "cuda"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--case", action="append", choices=FORMAL_CASE_NAMES)
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
    try:
        summary = run_campaign(arguments)
    except Exception as exc:
        arguments.output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            arguments.output_dir / "campaign_summary.json",
            {
                "schema_version": "moirai2-p8-runtime-campaign-v1",
                "status": "FAILED",
                "phase": "P8_RUNTIME_CAMPAIGN",
                "campaign_id": arguments.campaign_id,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "formal_runtime_certified": False,
            },
        )
        _write_json(
            arguments.output_dir / "ARTIFACT_MANIFEST.json",
            _artifact_manifest(arguments.output_dir),
        )
        write_sha256_manifest(
            arguments.output_dir,
            arguments.output_dir / "SHA256SUMS",
        )
        return 2
    return 0 if summary.get("status") in {"PASS", "PREPARED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
