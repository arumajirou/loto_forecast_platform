from __future__ import annotations

from pathlib import Path

from loto.probabilistic.kdpp_certification_gate import (
    sha256_file,
    tree_sha256,
    validate_history_bundle,
)
from loto.probabilistic.kdpp_history_source import validate_materialized_raw_history
from loto.probabilistic.kdpp_target_contracts import (
    _EXPORTER_FILES as _EXPORTER_FILES,
)
from loto.probabilistic.kdpp_target_contracts import (
    _KDPP_FILES as _KDPP_FILES,
)
from loto.probabilistic.kdpp_target_contracts import (
    ExecutionEvent,
    _write_json,
)
from loto.probabilistic.kdpp_target_event_core import _event_path as _event_path
from loto.probabilistic.kdpp_target_events import (
    _final_report_payload,
    _load_events,
    _record_event,
    _require_external_artifact,
    verify_control_workspace,
)
from loto.probabilistic.kdpp_target_plan import _load_plan, prepare_workspace
from loto.probabilistic.kdpp_target_runtime import _validate_cpu_formal

__all__ = [
    "prepare_workspace",
    "record_cpu_formal",
    "record_kdpp_history",
    "record_source_handoff",
    "verify_control_workspace",
]


def record_source_handoff(workspace: Path, handoff_root: Path) -> ExecutionEvent:
    plan = _load_plan(workspace.resolve())
    handoff_root = handoff_root.resolve()
    _require_external_artifact(handoff_root, plan, "source handoff")
    handoff, approval, verification = validate_materialized_raw_history(handoff_root)
    return _record_event(
        workspace,
        stage="SOURCE_HANDOFF_RECORDED",
        artifact_paths={"source_handoff": str(handoff_root)},
        artifact_sha256={"source_handoff_tree_sha256": tree_sha256(handoff_root)},
        summary={
            "reviewer": approval.reviewer,
            "reviewed_at": approval.reviewed_at,
            "game_count": len(verification.games),
            "source_export_root": handoff.source_export_root,
            "future_actuals_used": False,
            "raw_data_modified": False,
        },
    )


def record_kdpp_history(
    workspace: Path,
    bundle: Path,
    approval_path: Path,
) -> ExecutionEvent:
    plan = _load_plan(workspace.resolve())
    bundle = bundle.resolve()
    approval_path = approval_path.resolve()
    _require_external_artifact(bundle, plan, "k-DPP history bundle")
    _require_external_artifact(approval_path, plan, "k-DPP history approval")
    manifest, approval, item_ids = validate_history_bundle(bundle, approval_path)
    if manifest.game != plan.game or manifest.position != plan.position:
        raise ValueError("approved k-DPP history does not match the control plan")
    return _record_event(
        workspace,
        stage="KDPP_HISTORY_RECORDED",
        artifact_paths={"bundle": str(bundle), "approval": str(approval_path)},
        artifact_sha256={
            "bundle_tree_sha256": tree_sha256(bundle),
            "approval_sha256": sha256_file(approval_path),
        },
        summary={
            "game": manifest.game,
            "position": manifest.position,
            "row_count": manifest.row_count,
            "item_count": len(item_ids),
            "cardinality": manifest.cardinality,
            "reviewer": approval.reviewer,
            "reviewed_at_utc": approval.reviewed_at_utc.isoformat(),
        },
    )


def record_cpu_formal(workspace: Path, runtime_workspace: Path) -> ExecutionEvent:
    workspace = workspace.resolve()
    plan = _load_plan(workspace)
    runtime_workspace = runtime_workspace.resolve()
    _require_external_artifact(runtime_workspace, plan, "runtime workspace")
    summary = _validate_cpu_formal(runtime_workspace, plan=plan)
    event = _record_event(
        workspace,
        stage="CPU_FORMAL_RECORDED",
        artifact_paths={"runtime_workspace": str(runtime_workspace)},
        artifact_sha256={
            "runtime_tree_sha256": tree_sha256(runtime_workspace),
            "formal_report_sha256": summary["report_sha256"],
        },
        summary=summary,
    )
    report_path = workspace / "TARGET_EXECUTION_REPORT.json"
    if report_path.exists():
        raise FileExistsError(report_path)
    events = _load_events(workspace, plan)
    _write_json(report_path, _final_report_payload(plan, events))
    verify_control_workspace(workspace)
    return event
