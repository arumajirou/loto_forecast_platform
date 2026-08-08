from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.probabilistic.kdpp_target_contracts import (
    MODEL_ID,
    SCHEMA_VERSION,
    ExecutionEvent,
    TargetExecutionPlan,
    _sha256_bytes,
    canonical_json_bytes,
)
from loto.probabilistic.kdpp_target_repository import _is_within


def _event_payload_hash(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("event_sha256", None)
    return _sha256_bytes(canonical_json_bytes(unsigned))


def _event_path(workspace: Path, index: int, stage: str) -> Path:
    slug = stage.lower().replace("_", "-")
    return workspace / "events" / f"{index:03d}-{slug}.json"


def _require_external_artifact(path: Path, plan: TargetExecutionPlan, label: str) -> None:
    if _is_within(path, Path(plan.exporter.root)) or _is_within(path, Path(plan.kdpp.root)):
        raise ValueError(f"{label} must be outside both source repositories")


def _final_report_payload(
    plan: TargetExecutionPlan,
    events: tuple[ExecutionEvent, ...],
) -> dict[str, Any]:
    runtime = events[-1].summary
    return {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "status": "PASS",
        "certification_class": "CPU_FORMAL",
        "formal_runtime_certification": True,
        "run_id": plan.run_id,
        "source_revision": plan.source_revision,
        "game": plan.game,
        "position": plan.position,
        "prediction_length": plan.prediction_length,
        "event_sha256": [event.event_sha256 for event in events],
        "runtime_summary": runtime,
        "holdout_opened": False,
        "prospective_opened": False,
        "public_registration_performed": False,
        "oof_executed": False,
    }
