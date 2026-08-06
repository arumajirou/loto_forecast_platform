from __future__ import annotations

from collections import defaultdict

from loto.data_access_ledger._common import finding
from loto.data_access_ledger.contracts import AccessEvent, DataAccessLedger
from loto.data_access_ledger.enums import (
    AccessOperation,
    DataRole,
    FindingCode,
    Stage,
)
from loto.data_access_ledger.report import ValidationFinding


def validate_prospective_and_holdout(
    ledger: DataAccessLedger,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    by_forecast: dict[str, list[AccessEvent]] = defaultdict(list)
    for event in ledger.events:
        if event.forecast_id is not None:
            by_forecast[event.forecast_id].append(event)

        if event.operation is AccessOperation.PREDICT:
            actual_slices = [
                item.dataset_id
                for item in event.input_slices
                if item.data_role is DataRole.ACTUALS or item.contains_actuals
            ]
            actual_states = [
                item.state_id for item in event.input_states if item.contains_actuals
            ]
            if actual_slices or actual_states:
                findings.append(
                    finding(
                        FindingCode.PROSPECTIVE_ACTUAL_LEAKAGE,
                        event_id=event.event_id,
                        message="prediction cannot consume actual-bearing slices or states",
                        observed=str(actual_slices + actual_states),
                    )
                )

    for forecast_id, events in by_forecast.items():
        events.sort(key=lambda item: item.sequence_no)
        predicts = [item for item in events if item.operation is AccessOperation.PREDICT]
        locks = [
            item for item in events if item.operation is AccessOperation.LOCK_PREDICTION
        ]
        reads = [
            item for item in events if item.operation is AccessOperation.READ_ACTUALS
        ]
        scores = [item for item in events if item.operation is AccessOperation.SCORE]

        for lock in locks:
            if not any(item.sequence_no < lock.sequence_no for item in predicts):
                findings.append(
                    finding(
                        FindingCode.LOCK_BEFORE_PREDICT_MISSING,
                        event_id=lock.event_id,
                        message="LOCK_PREDICTION requires an earlier PREDICT",
                        observed=forecast_id,
                    )
                )
        for read in reads:
            if not any(item.sequence_no < read.sequence_no for item in predicts):
                findings.append(
                    finding(
                        FindingCode.PROSPECTIVE_ACTUAL_LEAKAGE,
                        event_id=read.event_id,
                        message="READ_ACTUALS occurred before the corresponding PREDICT",
                        observed=forecast_id,
                    )
                )
            if not any(item.sequence_no < read.sequence_no for item in locks):
                findings.append(
                    finding(
                        FindingCode.ACTUAL_READ_BEFORE_LOCK,
                        event_id=read.event_id,
                        message="READ_ACTUALS requires an earlier LOCK_PREDICTION",
                        observed=forecast_id,
                    )
                )
            if read.stage is Stage.HOLDOUT and not any(
                item.sequence_no < read.sequence_no and item.stage is Stage.HOLDOUT
                for item in predicts
            ):
                findings.append(
                    finding(
                        FindingCode.HOLDOUT_LEAKAGE,
                        event_id=read.event_id,
                        message="Holdout actual read requires an earlier Holdout prediction",
                        observed=forecast_id,
                    )
                )
            for item in read.input_slices:
                if item.draw_id is not None and item.draw_id != forecast_id:
                    findings.append(
                        finding(
                            FindingCode.ACTUAL_IDENTITY_MISMATCH,
                            event_id=read.event_id,
                            message="actual draw identity does not match forecast identity",
                            expected=forecast_id,
                            observed=item.draw_id,
                        )
                    )
        for score in scores:
            if not any(item.sequence_no < score.sequence_no for item in reads):
                findings.append(
                    finding(
                        FindingCode.SCORE_BEFORE_ACTUAL_READ,
                        event_id=score.event_id,
                        message="SCORE requires an earlier READ_ACTUALS",
                        observed=forecast_id,
                    )
                )
            if not any(item.sequence_no < score.sequence_no for item in locks):
                findings.append(
                    finding(
                        FindingCode.LOCK_BEFORE_PREDICT_MISSING,
                        event_id=score.event_id,
                        message="SCORE requires an earlier prediction lock",
                        observed=forecast_id,
                    )
                )
    return findings
