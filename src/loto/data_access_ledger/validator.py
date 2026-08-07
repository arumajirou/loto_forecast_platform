from __future__ import annotations

from loto.data_access_ledger._common import INVALID_CODES
from loto.data_access_ledger.contracts import DataAccessLedger
from loto.data_access_ledger.enums import (
    AccessDecision,
    FindingSeverity,
)
from loto.data_access_ledger.report import ValidationReport
from loto.data_access_ledger.rules_fit import validate_fit_tune_and_availability
from loto.data_access_ledger.rules_oof import validate_oof
from loto.data_access_ledger.rules_prospective import validate_prospective_and_holdout
from loto.data_access_ledger.rules_state import validate_state_provenance
from loto.data_access_ledger.rules_structure import validate_structure


def validate_ledger(ledger: DataAccessLedger) -> ValidationReport:
    findings = [
        *validate_structure(ledger),
        *validate_state_provenance(ledger),
        *validate_fit_tune_and_availability(ledger),
        *validate_oof(ledger),
        *validate_prospective_and_holdout(ledger),
    ]
    findings.sort(key=lambda item: (item.event_id, item.code.value, item.message))
    error_count = sum(item.severity is FindingSeverity.ERROR for item in findings)
    warning_count = sum(item.severity is FindingSeverity.WARNING for item in findings)
    if error_count:
        status = (
            AccessDecision.INVALID
            if any(item.code in INVALID_CODES for item in findings)
            else AccessDecision.BLOCKED
        )
    else:
        status = AccessDecision.PASS
    return ValidationReport(
        status=status,
        run_id=ledger.run_id,
        ledger_sha256=ledger.ledger_sha256,
        findings=findings,
        error_count=error_count,
        warning_count=warning_count,
        verified_event_count=len(ledger.events),
    )
