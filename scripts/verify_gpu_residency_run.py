#!/usr/bin/env python3
"""Verify one Forecast MCP adaptive-residency run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_checksums(run_dir: Path) -> list[str]:
    checksum_path = run_dir / "SHA256SUMS"
    if not checksum_path.is_file():
        return ["SHA256SUMS missing"]
    errors: list[str] = []
    for raw in checksum_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        digest, relative = raw.split("  ", 1)
        target = run_dir / relative
        if not target.is_file():
            errors.append(f"missing artifact: {relative}")
        elif _sha256_file(target) != digest:
            errors.append(f"checksum mismatch: {relative}")
    return errors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--expected-mode", choices=["coexist", "handoff"])
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    errors = _verify_checksums(args.run_dir)
    result_path = args.run_dir / "FORECAST_MCP_RESULT.json"
    if not result_path.is_file():
        errors.append("FORECAST_MCP_RESULT.json missing")
        payload: dict[str, Any] = {}
    else:
        payload = json.loads(result_path.read_text(encoding="utf-8"))

    residency = payload.get("gpu_residency")
    if payload.get("status") != "PASS":
        errors.append("result status is not PASS")
    if not isinstance(residency, dict):
        errors.append("gpu_residency evidence missing")
        selected = None
    else:
        selected = residency.get("selected_mode")
        if args.expected_mode and selected != args.expected_mode:
            errors.append(
                f"selected_mode={selected!r}, expected={args.expected_mode!r}"
            )
        if selected == "coexist":
            if residency.get("qwen_stopped") is not False:
                errors.append("COEXIST qwen_stopped must be false")
            if residency.get("qwen_restored") is not False:
                errors.append("COEXIST qwen_restored must be false")
            if residency.get("llm_continuity_verified") is not True:
                errors.append("COEXIST continuity evidence missing")
        elif selected == "handoff":
            if residency.get("qwen_stopped") is not True:
                errors.append("HANDOFF qwen_stopped must be true")
            if residency.get("qwen_restored") is not True:
                errors.append("HANDOFF qwen_restored must be true")
        else:
            errors.append(f"unexpected selected residency mode: {selected!r}")

    supervisor = payload.get("supervisor")
    if not isinstance(supervisor, dict) or supervisor.get("gate_reopened") is not True:
        errors.append("gate_reopened evidence missing")
    runtime = payload.get("runtime_evidence")
    gpu = payload.get("gpu_evidence")
    if not isinstance(runtime, dict) or runtime.get("cpu_fallback") is not False:
        errors.append("runtime cpu_fallback=false evidence missing")
    if not isinstance(gpu, dict) or gpu.get("cpu_fallback") is not False:
        errors.append("GPU cpu_fallback=false evidence missing")
    prediction_sha = payload.get("prediction_sha256")
    if not isinstance(prediction_sha, str) or len(prediction_sha) != 64:
        errors.append("prediction SHA-256 evidence missing")

    verdict = {
        "status": "PASS" if not errors else "FAILED",
        "run_dir": str(args.run_dir),
        "selected_mode": selected,
        "errors": errors,
    }
    print(json.dumps(verdict, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
