from __future__ import annotations

from loto.data_access_ledger._common import (
    AVAILABILITY_OPERATIONS,
    STATE_PRODUCER,
    finding,
)
from loto.data_access_ledger.contracts import AccessEvent, DataAccessLedger, StateReference
from loto.data_access_ledger.enums import FindingCode
from loto.data_access_ledger.report import ValidationFinding


def _matching_slice(event: AccessEvent, state: StateReference) -> bool:
    return any(
        item.dataset_sha256 == state.fitted_dataset_sha256
        and item.data_role is state.fitted_data_role
        and item.row_start == state.fitted_row_start
        and item.row_end == state.fitted_row_end
        for item in event.input_slices
    )


def validate_state_provenance(ledger: DataAccessLedger) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    producers: dict[str, tuple[AccessEvent, StateReference]] = {}
    for event in ledger.events:
        state = event.output_state
        if state is None:
            continue
        if state.state_id in producers:
            previous = producers[state.state_id][0]
            findings.append(
                finding(
                    FindingCode.STATE_PROVENANCE_MISMATCH,
                    event_id=event.event_id,
                    related=[previous.event_id],
                    message="state_id is produced more than once",
                    observed=state.state_id,
                )
            )
        else:
            producers[state.state_id] = (event, state)
        if state.fitted_event_id != event.event_id:
            findings.append(
                finding(
                    FindingCode.STATE_PROVENANCE_MISMATCH,
                    event_id=event.event_id,
                    message="output state fitted_event_id must identify its producer",
                    expected=event.event_id,
                    observed=state.fitted_event_id,
                )
            )
        expected_operation = STATE_PRODUCER[state.state_kind]
        if event.operation is not expected_operation:
            findings.append(
                finding(
                    FindingCode.STATE_PROVENANCE_MISMATCH,
                    event_id=event.event_id,
                    message="output state kind does not match producer operation",
                    expected=expected_operation.value,
                    observed=event.operation.value,
                )
            )
        if not _matching_slice(event, state):
            findings.append(
                finding(
                    FindingCode.STATE_PROVENANCE_MISMATCH,
                    event_id=event.event_id,
                    message="output state dataset provenance does not match producer inputs",
                    observed=state.state_id,
                )
            )
        if state.bound_run_id != event.run_id:
            findings.append(
                finding(
                    FindingCode.STATE_PROVENANCE_MISMATCH,
                    event_id=event.event_id,
                    message="new output state must be bound to producer run",
                    expected=event.run_id,
                    observed=state.bound_run_id,
                )
            )

    for event in ledger.events:
        for state in event.input_states:
            producer_pair = producers.get(state.state_id)
            if producer_pair is None:
                findings.append(
                    finding(
                        FindingCode.STATE_USED_BEFORE_FIT,
                        event_id=event.event_id,
                        message="input state has no producing event",
                        observed=state.state_id,
                    )
                )
                continue
            producer, produced_state = producer_pair
            if producer.sequence_no >= event.sequence_no:
                findings.append(
                    finding(
                        FindingCode.STATE_USED_BEFORE_FIT,
                        event_id=event.event_id,
                        related=[producer.event_id],
                        message="state producer does not precede state consumer",
                        expected=f"producer sequence < {event.sequence_no}",
                        observed=str(producer.sequence_no),
                    )
                )
            if state != produced_state:
                findings.append(
                    finding(
                        FindingCode.STATE_PROVENANCE_MISMATCH,
                        event_id=event.event_id,
                        related=[producer.event_id],
                        message="input state does not exactly match produced state evidence",
                        observed=state.state_id,
                    )
                )
            if state.fitted_event_id != producer.event_id:
                findings.append(
                    finding(
                        FindingCode.STATE_PROVENANCE_MISMATCH,
                        event_id=event.event_id,
                        related=[producer.event_id],
                        message="fitted_event_id does not identify producer",
                        expected=producer.event_id,
                        observed=state.fitted_event_id,
                    )
                )
            expected_operation = STATE_PRODUCER[state.state_kind]
            if producer.operation is not expected_operation:
                findings.append(
                    finding(
                        FindingCode.STATE_PROVENANCE_MISMATCH,
                        event_id=event.event_id,
                        related=[producer.event_id],
                        message="state kind does not match producer operation",
                        expected=expected_operation.value,
                        observed=producer.operation.value,
                    )
                )
            if not _matching_slice(producer, state):
                findings.append(
                    finding(
                        FindingCode.STATE_PROVENANCE_MISMATCH,
                        event_id=event.event_id,
                        related=[producer.event_id],
                        message="state fitted dataset provenance does not match producer inputs",
                        observed=state.state_id,
                    )
                )
            if (
                state.bound_run_id != event.run_id
                and event.run_id not in state.authorized_reuse_run_ids
            ):
                findings.append(
                    finding(
                        FindingCode.STATE_PROVENANCE_MISMATCH,
                        event_id=event.event_id,
                        related=[producer.event_id],
                        message="state is not bound or explicitly reusable by this run",
                        expected=event.run_id,
                        observed=state.bound_run_id,
                    )
                )
            if state.contains_actuals and event.operation in AVAILABILITY_OPERATIONS:
                findings.append(
                    finding(
                        FindingCode.ACTUAL_STATE_REUSE,
                        event_id=event.event_id,
                        related=[producer.event_id],
                        message=(
                            "actual-bearing state cannot be reused for fit, tune, "
                            "calibrate, or predict"
                        ),
                        observed=state.state_id,
                    )
                )
            if event.forecast_origin is not None:
                late_inputs = [
                    item.dataset_id
                    for item in producer.input_slices
                    if item.available_at > event.forecast_origin
                ]
                if late_inputs:
                    findings.append(
                        finding(
                            FindingCode.STATE_PROVENANCE_MISMATCH,
                            event_id=event.event_id,
                            related=[producer.event_id],
                            message=(
                                "state was fitted with data unavailable at consumer "
                                "forecast origin"
                            ),
                            expected=(
                                f"available_at <= {event.forecast_origin.isoformat()}"
                            ),
                            observed=",".join(late_inputs),
                        )
                    )
    return findings
