from __future__ import annotations

from collections import defaultdict

from loto.data_access_ledger._common import finding
from loto.data_access_ledger.canonical import compute_ledger_sha256
from loto.data_access_ledger.contracts import AccessEvent, DataAccessLedger
from loto.data_access_ledger.enums import FindingCode
from loto.data_access_ledger.report import ValidationFinding


def _detect_cycle(events: list[AccessEvent]) -> list[str] | None:
    parents = {event.event_id: event.parent_event_ids for event in events}
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(event_id: str) -> list[str] | None:
        if event_id in visiting:
            index = stack.index(event_id)
            return [*stack[index:], event_id]
        if event_id in visited:
            return None
        visiting.add(event_id)
        stack.append(event_id)
        for parent_id in parents.get(event_id, []):
            if parent_id not in parents:
                continue
            cycle = visit(parent_id)
            if cycle is not None:
                return cycle
        stack.pop()
        visiting.remove(event_id)
        visited.add(event_id)
        return None

    for event_id in parents:
        cycle = visit(event_id)
        if cycle is not None:
            return cycle
    return None


def validate_structure(ledger: DataAccessLedger) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    ids = [event.event_id for event in ledger.events]
    if len(ids) != len(set(ids)):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        findings.append(
            finding(
                FindingCode.EVENT_ID_DUPLICATE,
                message="event_id values are not unique",
                expected="unique event_id values",
                observed=",".join(duplicates),
            )
        )

    listed_sequences = [event.sequence_no for event in ledger.events]
    expected_sequences = list(range(1, len(ledger.events) + 1))
    if sorted(listed_sequences) != expected_sequences:
        findings.append(
            finding(
                FindingCode.EVENT_SEQUENCE_GAP,
                message="sequence_no must be gap-free from 1",
                expected=str(expected_sequences),
                observed=str(listed_sequences),
            )
        )
    elif listed_sequences != expected_sequences:
        findings.append(
            finding(
                FindingCode.EVENT_ORDER_MISMATCH,
                message="event list order must match sequence_no order",
                expected=str(expected_sequences),
                observed=str(listed_sequences),
            )
        )

    if ledger.event_count != len(ledger.events):
        findings.append(
            finding(
                FindingCode.EVENT_COUNT_MISMATCH,
                message="event_count does not match events",
                expected=str(len(ledger.events)),
                observed=str(ledger.event_count),
            )
        )
    if ledger.first_event_at != ledger.events[0].occurred_at:
        findings.append(
            finding(
                FindingCode.EVENT_TIME_BOUNDARY_MISMATCH,
                message="first_event_at does not match first event",
                expected=ledger.events[0].occurred_at.isoformat(),
                observed=ledger.first_event_at.isoformat(),
            )
        )
    if ledger.last_event_at != ledger.events[-1].occurred_at:
        findings.append(
            finding(
                FindingCode.EVENT_TIME_BOUNDARY_MISMATCH,
                message="last_event_at does not match last event",
                expected=ledger.events[-1].occurred_at.isoformat(),
                observed=ledger.last_event_at.isoformat(),
            )
        )

    expected_hash = compute_ledger_sha256(ledger)
    if ledger.ledger_sha256 != expected_hash:
        findings.append(
            finding(
                FindingCode.LEDGER_HASH_MISMATCH,
                message="ledger content does not match ledger_sha256",
                expected=expected_hash,
                observed=ledger.ledger_sha256,
            )
        )

    events_by_id: dict[str, AccessEvent] = {}
    for event in ledger.events:
        events_by_id.setdefault(event.event_id, event)
        if event.run_id != ledger.run_id:
            findings.append(
                finding(
                    FindingCode.RUN_ID_MISMATCH,
                    event_id=event.event_id,
                    message="event run_id does not match ledger run_id",
                    expected=ledger.run_id,
                    observed=event.run_id,
                )
            )

    for previous, current in zip(ledger.events, ledger.events[1:], strict=False):
        if current.occurred_at < previous.occurred_at:
            findings.append(
                finding(
                    FindingCode.TIMESTAMP_ORDER_VIOLATION,
                    event_id=current.event_id,
                    related=[previous.event_id],
                    message="event timestamps move backwards",
                    expected=f">={previous.occurred_at.isoformat()}",
                    observed=current.occurred_at.isoformat(),
                )
            )

    for event in ledger.events:
        for parent_id in event.parent_event_ids:
            parent = events_by_id.get(parent_id)
            if parent is None:
                findings.append(
                    finding(
                        FindingCode.EVENT_PARENT_MISSING,
                        event_id=event.event_id,
                        message="parent event is missing",
                        observed=parent_id,
                    )
                )
            elif parent.sequence_no >= event.sequence_no:
                findings.append(
                    finding(
                        FindingCode.EVENT_PARENT_NOT_PREVIOUS,
                        event_id=event.event_id,
                        related=[parent.event_id],
                        message="parent event must precede child event",
                        expected=f"sequence_no < {event.sequence_no}",
                        observed=str(parent.sequence_no),
                    )
                )

    cycle = _detect_cycle(ledger.events)
    if cycle is not None:
        findings.append(
            finding(
                FindingCode.EVENT_GRAPH_CYCLE,
                related=cycle,
                message="parent event graph contains a cycle",
                observed=" -> ".join(cycle),
            )
        )

    hashes_by_dataset: dict[str, set[str]] = defaultdict(set)
    for event in ledger.events:
        for item in event.input_slices:
            hashes_by_dataset[item.dataset_id].add(item.dataset_sha256)
    for dataset_id, hashes in hashes_by_dataset.items():
        if len(hashes) > 1:
            findings.append(
                finding(
                    FindingCode.DATASET_HASH_MISMATCH,
                    message="one dataset_id resolves to multiple SHA-256 values",
                    expected="one immutable hash per dataset_id",
                    observed=f"{dataset_id}:{sorted(hashes)}",
                )
            )
    return findings
