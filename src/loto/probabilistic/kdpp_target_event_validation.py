from __future__ import annotations

from pathlib import Path

from loto.probabilistic.kdpp_certification_gate import (
    sha256_file,
    tree_sha256,
    validate_history_bundle,
)
from loto.probabilistic.kdpp_history_source import validate_materialized_raw_history
from loto.probabilistic.kdpp_target_contracts import (
    STAGES,
    ControlState,
    ExecutionEvent,
    TargetExecutionPlan,
    _load_object,
)
from loto.probabilistic.kdpp_target_event_core import (
    _event_path,
    _event_payload_hash,
    _final_report_payload,
)
from loto.probabilistic.kdpp_target_plan import _load_plan
from loto.probabilistic.kdpp_target_runtime import _validate_cpu_formal


def _validate_event_artifact(
    event: ExecutionEvent,
    *,
    plan: TargetExecutionPlan,
) -> None:
    if event.stage == "SOURCE_HANDOFF_RECORDED":
        root = Path(event.artifact_paths["source_handoff"])
        handoff, approval, verification = validate_materialized_raw_history(root)
        expected = {"source_handoff_tree_sha256": tree_sha256(root)}
        if event.artifact_sha256 != expected:
            raise ValueError("source handoff event hash changed")
        if event.summary.get("reviewer") != approval.reviewer:
            raise ValueError("source handoff event reviewer changed")
        if event.summary.get("game_count") != len(verification.games):
            raise ValueError("source handoff event game count changed")
        if event.summary.get("source_export_root") != handoff.source_export_root:
            raise ValueError("source handoff event export identity changed")
        return
    if event.stage == "KDPP_HISTORY_RECORDED":
        bundle = Path(event.artifact_paths["bundle"])
        approval_path = Path(event.artifact_paths["approval"])
        manifest, approval, item_ids = validate_history_bundle(bundle, approval_path)
        expected = {
            "bundle_tree_sha256": tree_sha256(bundle),
            "approval_sha256": sha256_file(approval_path),
        }
        if event.artifact_sha256 != expected:
            raise ValueError("k-DPP history event bytes changed")
        if manifest.game != plan.game or manifest.position != plan.position:
            raise ValueError("k-DPP history event geometry changed")
        if event.summary.get("reviewer") != approval.reviewer:
            raise ValueError("k-DPP history reviewer changed")
        if event.summary.get("item_count") != len(item_ids):
            raise ValueError("k-DPP history item count changed")
        return
    runtime = Path(event.artifact_paths["runtime_workspace"])
    summary = _validate_cpu_formal(runtime, plan=plan)
    expected = {
        "runtime_tree_sha256": tree_sha256(runtime),
        "formal_report_sha256": summary["report_sha256"],
    }
    if event.artifact_sha256 != expected:
        raise ValueError("CPU_FORMAL runtime event bytes changed")
    if event.summary != summary:
        raise ValueError("CPU_FORMAL runtime summary changed")


def _load_events(workspace: Path, plan: TargetExecutionPlan) -> tuple[ExecutionEvent, ...]:
    events_root = workspace / "events"
    for path in events_root.iterdir():
        if path.is_symlink() or path.is_dir() or path.suffix != ".json":
            raise ValueError("events directory contains an unsupported entry")
    event_paths = sorted(events_root.glob("*.json"))
    events: list[ExecutionEvent] = []
    previous: str | None = None
    for expected_index, path in enumerate(event_paths, start=1):
        event = ExecutionEvent.model_validate(_load_object(path))
        if event.event_index != expected_index or event.stage != STAGES[expected_index - 1]:
            raise ValueError("event order or stage mismatch")
        if path != _event_path(workspace, expected_index, event.stage):
            raise ValueError("event filename mismatch")
        if event.run_id != plan.run_id or event.previous_event_sha256 != previous:
            raise ValueError("event chain identity mismatch")
        if _event_payload_hash(event.model_dump(mode="json")) != event.event_sha256:
            raise ValueError("event SHA-256 mismatch")
        _validate_event_artifact(event, plan=plan)
        previous = event.event_sha256
        events.append(event)
    return tuple(events)


def verify_control_workspace(workspace: Path) -> ControlState:
    workspace = workspace.resolve()
    plan = _load_plan(workspace)
    events = _load_events(workspace, plan)
    state = ControlState.model_validate(_load_object(workspace / "STATE.json"))
    expected_stage = "PREPARED" if not events else events[-1].stage
    expected_hash = None if not events else events[-1].event_sha256
    if (
        state.run_id != plan.run_id
        or state.event_count != len(events)
        or state.current_stage != expected_stage
        or state.last_event_sha256 != expected_hash
    ):
        raise ValueError("mutable state does not match the immutable event chain")
    report_path = workspace / "TARGET_EXECUTION_REPORT.json"
    if state.current_stage == "CPU_FORMAL_RECORDED":
        expected_report = _final_report_payload(plan, events)
        if _load_object(report_path) != expected_report:
            raise ValueError("target execution report differs from the event chain")
    elif report_path.exists():
        raise ValueError("target execution report exists before CPU_FORMAL")
    return state


