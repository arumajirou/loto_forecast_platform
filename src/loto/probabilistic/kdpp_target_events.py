from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.probabilistic.kdpp_target_contracts import (
    MODEL_ID,
    SCHEMA_VERSION,
    STAGES,
    ControlState,
    ExecutionEvent,
    _write_json,
    now_utc,
)
from loto.probabilistic.kdpp_target_event_core import (
    _event_path,
    _event_payload_hash,
    _final_report_payload,
    _require_external_artifact,
)
from loto.probabilistic.kdpp_target_event_validation import (
    _load_events,
    verify_control_workspace,
)


def _record_event(
    workspace: Path,
    *,
    stage: str,
    artifact_paths: dict[str, str],
    artifact_sha256: dict[str, str],
    summary: dict[str, Any],
) -> ExecutionEvent:
    workspace = workspace.resolve()
    state = verify_control_workspace(workspace)
    expected_stage = STAGES[state.event_count]
    if stage != expected_stage:
        raise ValueError(f"expected next stage {expected_stage}, got {stage}")
    index = state.event_count + 1
    payload = {
        "schema_version": SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "run_id": state.run_id,
        "event_index": index,
        "stage": stage,
        "recorded_at_utc": now_utc().isoformat().replace("+00:00", "Z"),
        "previous_event_sha256": state.last_event_sha256,
        "artifact_paths": artifact_paths,
        "artifact_sha256": artifact_sha256,
        "summary": summary,
    }
    payload["event_sha256"] = _event_payload_hash(payload)
    event = ExecutionEvent.model_validate(payload)
    event_path = _event_path(workspace, index, stage)
    if event_path.exists():
        raise FileExistsError(event_path)
    _write_json(event_path, event)
    next_state = ControlState(
        schema_version=SCHEMA_VERSION,
        model_id=MODEL_ID,
        run_id=state.run_id,
        current_stage=stage,
        event_count=index,
        last_event_sha256=event.event_sha256,
    )
    _write_json(workspace / "STATE.json", next_state)
    if stage != "CPU_FORMAL_RECORDED":
        verify_control_workspace(workspace)
    return event


__all__ = [
    "_final_report_payload",
    "_load_events",
    "_record_event",
    "_require_external_artifact",
    "verify_control_workspace",
]
