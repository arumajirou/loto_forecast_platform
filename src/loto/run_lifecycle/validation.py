"""Machine-readable lifecycle validation reports."""

from __future__ import annotations

from collections.abc import Iterable

from .events import verify_event_chain
from .exceptions import EventChainError
from .models import (
    FindingSeverity,
    LifecycleValidationFinding,
    LifecycleValidationReport,
    RunEvent,
)


def validate_lifecycle(events: Iterable[RunEvent]) -> LifecycleValidationReport:
    ordered = tuple(events)
    findings: list[LifecycleValidationFinding] = []
    try:
        verified = verify_event_chain(ordered)
    except EventChainError as exc:
        findings.append(
            LifecycleValidationFinding(
                code="event-chain-invalid",
                severity=FindingSeverity.ERROR,
                message=str(exc),
            )
        )
        verified = ()
    if not ordered:
        findings.append(
            LifecycleValidationFinding(
                code="empty-event-chain",
                severity=FindingSeverity.WARNING,
                message="No lifecycle event has been recorded.",
            )
        )
    return LifecycleValidationReport(
        valid=not any(item.severity == FindingSeverity.ERROR for item in findings),
        findings=tuple(findings),
        validated_event_count=len(verified),
        chain_head_sha256=verified[-1].event_sha256 if verified else None,
    )
