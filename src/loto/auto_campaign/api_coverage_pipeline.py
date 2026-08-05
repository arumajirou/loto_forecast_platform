"""Integrated API coverage execution and coverage-state resolution.

The pipeline preserves the existing API coverage artifacts and legacy top-level
status while adding the CPU-safe coverage-state bundle. GPU runtime remains a
separate ``EXECUTION_PENDING`` boundary.
"""

from __future__ import annotations

import json
import shutil
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .api_coverage import run_api_coverage
from .contracts import CampaignConfig
from .coverage_state import VerificationStatus, write_coverage_state_bundle
from .persistence import write_json, write_sha256s


def _load_api_results(run_root: Path) -> list[dict[str, Any]]:
    result_path = run_root / "API_ARGUMENT_COVERAGE_RESULT.parquet"
    if not result_path.is_file():
        raise FileNotFoundError(result_path)
    return pd.read_parquet(result_path).to_dict(orient="records")


def _write_integrated_manifest(
    run_root: Path,
    base_manifest: dict[str, Any],
    coverage_state: dict[str, Any],
) -> dict[str, Any]:
    failed = coverage_state["status"] == VerificationStatus.FAILED.value
    coverage_state_path = (
        "coverage_state_failure.json" if failed else "coverage-state/manifest.json"
    )
    manifest = {
        **base_manifest,
        "coverage_state_schema_version": coverage_state.get("schema_version"),
        "coverage_state_status": coverage_state["status"],
        "verification_status": coverage_state["status"],
        "coverage_state_path": coverage_state_path,
        "gpu_runtime_status": coverage_state.get(
            "gpu_runtime_status",
            VerificationStatus.EXECUTION_PENDING.value,
        ),
        "coverage_state": coverage_state,
    }
    if failed:
        manifest["status"] = "PARTIAL"
    write_json(run_root / "manifest.json", manifest)
    write_sha256s(run_root)
    return manifest


def run_api_coverage_pipeline(
    project_root: Path,
    config: CampaignConfig,
    run_root: Path,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    """Run API coverage and immediately resolve formal verification states.

    The existing ``run_api_coverage`` result remains authoritative for case
    execution. The resolver adds constructor/default-config evidence and writes
    a nested ``coverage-state`` bundle. Resolver failures are captured as
    artifacts and return a non-PASS top-level status instead of deleting or
    obscuring the completed API case results.
    """

    base_manifest = run_api_coverage(
        project_root,
        config,
        run_root,
        resume=resume,
    )
    coverage_root = run_root / "coverage-state"
    if coverage_root.exists():
        shutil.rmtree(coverage_root)

    try:
        api_results = _load_api_results(run_root)
        coverage_manifest = write_coverage_state_bundle(
            output_dir=coverage_root,
            api_results=api_results,
        )
    except Exception as exc:
        failure = {
            "schema_version": "all-auto-coverage-state-failure-v1",
            "created_at": datetime.now(UTC).isoformat(),
            "status": VerificationStatus.FAILED.value,
            "failed_phase": "coverage_state_resolution",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "gpu_runtime_status": VerificationStatus.EXECUTION_PENDING.value,
        }
        write_json(run_root / "coverage_state_failure.json", failure)
        return _write_integrated_manifest(run_root, base_manifest, failure)

    failure_path = run_root / "coverage_state_failure.json"
    if failure_path.exists():
        failure_path.unlink()
    return _write_integrated_manifest(run_root, base_manifest, coverage_manifest)


def load_integrated_manifest(run_root: Path) -> dict[str, Any]:
    """Read and validate the integrated manifest for downstream automation."""

    path = run_root / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "status",
        "coverage_state_status",
        "verification_status",
        "gpu_runtime_status",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"integrated API coverage manifest missing fields: {missing}")
    return payload
