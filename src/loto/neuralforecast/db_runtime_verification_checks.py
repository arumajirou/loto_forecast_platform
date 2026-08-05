"""Read-only, fail-closed checks for database NeuralForecast campaign artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db_runtime_verification_model_checks import verify_model
from .db_runtime_verification_models import DatabaseRuntimeVerificationReport


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json_object(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"{label} missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{label} unreadable: {type(exc).__name__}: {exc}")
        return {}
    if not isinstance(payload, dict):
        failures.append(f"{label} must be a JSON object: {path}")
        return {}
    return payload


def evaluate_database_runtime_run(
    run_directory: str | Path,
    *,
    expected_model_count: int | None = None,
    require_gpu: bool | None = None,
) -> DatabaseRuntimeVerificationReport:
    """Evaluate a completed database campaign without mutating model artifacts."""

    run_dir = Path(run_directory).resolve()
    failures: list[str] = []
    if not run_dir.is_dir():
        failures.append(f"run directory is missing: {run_dir}")
    campaign = read_json_object(run_dir / "campaign_report.json", failures, "campaign report")
    plan = read_json_object(run_dir / "campaign_plan.json", failures, "campaign plan")
    if not (run_dir / "input_panel.csv").is_file():
        failures.append("input_panel.csv is missing")

    rows = campaign.get("reports") if campaign else None
    if not isinstance(rows, list):
        failures.append("campaign reports must be a list")
        rows = []
    if expected_model_count is None:
        planned = plan.get("models") if isinstance(plan, Mapping) else None
        expected_model_count = (
            len(planned)
            if isinstance(planned, Sequence) and not isinstance(planned, str)
            else int(campaign.get("started_model_count") or len(rows))
        )
    if expected_model_count < 1:
        failures.append("expected_model_count must be >= 1")
    runtime_contract = plan.get("runtime_certification") if isinstance(plan, Mapping) else None
    if not isinstance(runtime_contract, Mapping):
        failures.append("campaign plan runtime_certification must be an object")
        runtime_contract = {}
    plan_gpu = runtime_contract.get("require_gpu_execution")
    resolved_require_gpu = bool(plan_gpu) if require_gpu is None else require_gpu
    if require_gpu is True and plan_gpu is not True:
        failures.append("verifier requires GPU but campaign plan does not require GPU execution")
    if require_gpu is False and plan_gpu is True:
        failures.append("verifier requires CPU but campaign plan requires GPU execution")

    for key, expected in (
        ("started_model_count", expected_model_count),
        ("succeeded_model_count", expected_model_count),
        ("runtime_certified_model_count", expected_model_count),
        ("failed_model_count", 0),
        ("search_space_verified_model_count", expected_model_count),
    ):
        if campaign.get(key) != expected:
            failures.append(
                f"campaign {key} mismatch: expected={expected}, actual={campaign.get(key)}"
            )
    if campaign.get("status") != "SUCCEEDED":
        failures.append(f"campaign status is not SUCCEEDED: {campaign.get('status')}")
    if campaign.get("certification_status") != "RUNTIME_CERTIFIED":
        failures.append(
            "campaign certification_status is not RUNTIME_CERTIFIED: "
            f"{campaign.get('certification_status')}"
        )
    if campaign.get("search_space_artifact_status") != "PASS":
        failures.append(
            "campaign search_space_artifact_status is not PASS: "
            f"{campaign.get('search_space_artifact_status')}"
        )

    invalid_rows = [index for index, row in enumerate(rows) if not isinstance(row, Mapping)]
    if invalid_rows:
        failures.append(f"campaign report rows are not objects: {invalid_rows}")
    model_results = tuple(
        verify_model(
            run_dir,
            row,
            require_gpu=resolved_require_gpu,
            read_json_object=read_json_object,
            sha256_file=sha256_file,
        )
        for row in rows
        if isinstance(row, Mapping)
    )
    if len(rows) != expected_model_count:
        failures.append(
            "campaign model row count mismatch: "
            f"expected={expected_model_count}, actual={len(rows)}"
        )
    model_ids = [result.model_id for result in model_results]
    if any(model_id == "<missing-model-id>" for model_id in model_ids):
        failures.append("one or more model IDs are missing")
    if len(set(model_ids)) != len(model_ids):
        failures.append("model IDs are duplicated")
    failed_models = [result.model_id for result in model_results if result.status != "PASS"]
    if failed_models:
        failures.append(f"model verification failed: {sorted(failed_models)}")

    return DatabaseRuntimeVerificationReport(
        created_at=datetime.now(UTC).isoformat(),
        run_directory=str(run_dir),
        status="PASS" if not failures else "FAIL",
        require_gpu=resolved_require_gpu,
        expected_model_count=expected_model_count,
        observed_model_count=len(rows),
        campaign_status=str(campaign.get("status") or "") or None,
        certification_status=str(campaign.get("certification_status") or "") or None,
        search_space_artifact_status=(
            str(campaign.get("search_space_artifact_status") or "") or None
        ),
        model_results=model_results,
        failures=tuple(failures),
    )
