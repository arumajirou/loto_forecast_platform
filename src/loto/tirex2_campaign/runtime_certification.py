from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from loto.adapters.tirex2.contracts import Tirex2Request, Tirex2Response


class ProcessRunEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    provider_pid: int
    exit_code: int
    response_path: str
    stdout_path: str
    stderr_path: str
    response_sha256: str


class RuntimeCertificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    lifecycle_status: str
    distinct_provider_pids: bool
    model_identity_match: bool
    artifact_identity_match: bool
    point_forecast_match: bool
    all_quantiles_match: bool
    series_identity_match: bool
    prediction_index_match: bool
    requested_device_match: bool
    no_cpu_fallback: bool
    run_a: ProcessRunEvidence
    run_b: ProcessRunEvidence
    blockers: list[str] = Field(default_factory=list)


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_responses(
    response_a: Tirex2Response,
    response_b: Tirex2Response,
    *,
    run_a: ProcessRunEvidence,
    run_b: ProcessRunEvidence,
) -> RuntimeCertificationResult:
    checks = {
        "distinct_provider_pids": (
            response_a.runtime_evidence.provider_pid != response_b.runtime_evidence.provider_pid
        ),
        "model_identity_match": response_a.model_identity == response_b.model_identity,
        "artifact_identity_match": (
            response_a.artifact_reference.snapshot_path
            == response_b.artifact_reference.snapshot_path
        ),
        "point_forecast_match": (
            _canonical_sha256(response_a.point_forecast)
            == _canonical_sha256(response_b.point_forecast)
        ),
        "all_quantiles_match": (
            _canonical_sha256(response_a.quantiles) == _canonical_sha256(response_b.quantiles)
        ),
        "series_identity_match": response_a.series_identity == response_b.series_identity,
        "prediction_index_match": response_a.prediction_index == response_b.prediction_index,
        "requested_device_match": (
            response_a.runtime_evidence.requested_device
            == response_b.runtime_evidence.requested_device
            == response_a.runtime_evidence.effective_device
            == response_b.runtime_evidence.effective_device
        ),
        "no_cpu_fallback": not (
            response_a.runtime_evidence.cpu_fallback or response_b.runtime_evidence.cpu_fallback
        ),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return RuntimeCertificationResult(
        status="PASS" if not blockers else "FAIL",
        lifecycle_status=(
            "BASE_SNAPSHOT_RELOADED_AND_PREDICTION_REPRODUCED"
            if not blockers
            else "RELOAD_CERTIFICATION_FAILED"
        ),
        run_a=run_a,
        run_b=run_b,
        blockers=blockers,
        **checks,
    )


def _run_once(
    request_path: Path,
    output_root: Path,
    label: str,
    provider_script: Path,
) -> tuple[Tirex2Response, ProcessRunEvidence]:
    run_root = output_root / label
    run_root.mkdir(parents=False, exist_ok=False)
    response_path = run_root / "response.json"
    stdout_path = run_root / "stdout.log"
    stderr_path = run_root / "stderr.log"
    completed = subprocess.run(
        [
            sys.executable,
            str(provider_script),
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"{label} provider process exited {completed.returncode}")
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    response = Tirex2Response.model_validate(payload)
    evidence = ProcessRunEvidence(
        label=label,
        provider_pid=response.runtime_evidence.provider_pid,
        exit_code=completed.returncode,
        response_path=str(response_path),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        response_sha256=_file_sha256(response_path),
    )
    return response, evidence


def certify_two_process_reload(
    request: Tirex2Request,
    output_root: Path,
    provider_script: Path,
) -> RuntimeCertificationResult:
    output_root.mkdir(parents=True, exist_ok=False)
    request_path = output_root / "request.json"
    request_path.write_text(
        json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    response_a, evidence_a = _run_once(request_path, output_root, "run-a", provider_script)
    response_b, evidence_b = _run_once(request_path, output_root, "run-b", provider_script)
    result = compare_responses(
        response_a,
        response_b,
        run_a=evidence_a,
        run_b=evidence_b,
    )
    result_path = output_root / "RUNTIME_CERTIFICATION.json"
    result_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _read_request(path: Path) -> Tirex2Request:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("request JSON must be an object")
    return Tirex2Request.model_validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify TiRex-2 two-process reload")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--provider-script", required=True, type=Path)
    args = parser.parse_args()
    result = certify_two_process_reload(
        _read_request(args.request),
        args.output_root,
        args.provider_script.resolve(strict=True),
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
