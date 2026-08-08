from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loto.orchestration.pipeline_ledger_types import (
    EventDraft,
    PipelineDatasetEvidence,
    PipelineLedgerCloseResult,
    atomic_write_json,
)


def seal_and_validate(
    run_id: str,
    created_at: datetime,
    evidence: PipelineDatasetEvidence,
    drafts: list[EventDraft],
    expected_seeds: list[int],
    output_dir: Path,
    coverage_gaps: list[str],
    complete: bool,
) -> PipelineLedgerCloseResult:
    from loto.data_access_ledger import (
        AccessDecision,
        AccessEvent,
        AccessOperation,
        DataRole,
        DatasetSlice,
        FoldRole,
        Stage,
        build_ledger,
        validate_ledger,
    )

    events: list[AccessEvent] = []
    for draft in drafts:
        converted: list[DatasetSlice] = []
        for item in draft.input_slices:
            converted.append(
                DatasetSlice(
                    dataset_id=item.dataset_id,
                    dataset_sha256=item.dataset_sha256,
                    data_role=DataRole(item.data_role),
                    game_id=evidence.game_id,
                    series_ids=list(evidence.series_ids),
                    row_start=item.row_start,
                    row_end=item.row_end,
                    observed_time_start=item.observed_time_start,
                    observed_time_end=item.observed_time_end,
                    available_at=item.available_at,
                    forecast_origin=item.forecast_origin,
                    contains_targets=item.contains_targets,
                    contains_actuals=item.contains_actuals,
                    immutable_source=True,
                    fold_id=item.fold_id,
                    fold_role=None if item.fold_role is None else FoldRole(item.fold_role),
                    draw_id=item.draw_id,
                )
            )
        events.append(
            AccessEvent(
                event_id=draft.event_id,
                run_id=run_id,
                sequence_no=draft.sequence_no,
                stage=Stage(draft.stage),
                operation=AccessOperation(draft.operation),
                occurred_at=draft.occurred_at,
                actor=draft.actor,
                input_slices=converted,
                parent_event_ids=list(draft.parent_event_ids),
                forecast_origin=draft.forecast_origin,
                forecast_id=draft.forecast_id,
                fold_id=draft.fold_id,
                seed=draft.seed,
                actuals_known=draft.actuals_known,
                notes=draft.notes,
            )
        )
    ledger = build_ledger(
        run_id=run_id,
        created_at=created_at,
        events=events,
        expected_seeds=expected_seeds,
    )
    validation = validate_ledger(ledger)
    status = (
        "PASS"
        if complete and not coverage_gaps and validation.status is AccessDecision.PASS
        else "BLOCKED"
    )
    ledger_path = output_dir / "pipeline_data_access_ledger.json"
    validation_path = output_dir / "pipeline_data_access_validation.json"
    report_path = output_dir / "pipeline_data_access_report.json"
    atomic_write_json(ledger_path, ledger.model_dump(mode="json"))
    atomic_write_json(validation_path, validation.model_dump(mode="json"))
    findings = [item.code.value for item in validation.findings]
    merged_gaps = list(dict.fromkeys([*coverage_gaps, *findings]))
    report = {
        "status": status,
        "run_id": run_id,
        "complete": complete,
        "runtime_interception": True,
        "ledger_path": str(ledger_path),
        "validation_path": str(validation_path),
        "ledger_sha256": ledger.ledger_sha256,
        "verified_events": validation.verified_event_count,
        "coverage_gaps": merged_gaps,
        "downstream_commit_executed": False,
    }
    atomic_write_json(report_path, report)
    return PipelineLedgerCloseResult(
        status=status,
        run_id=run_id,
        ledger_path=ledger_path,
        validation_path=validation_path,
        report_path=report_path,
        ledger_sha256=ledger.ledger_sha256,
        verified_events=validation.verified_event_count,
        coverage_gaps=tuple(merged_gaps),
    )
