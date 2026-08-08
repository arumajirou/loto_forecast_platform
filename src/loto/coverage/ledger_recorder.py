from __future__ import annotations

from loto.coverage.ledger_io import atomic_write_json
from loto.coverage.ledger_recorder_base import CoverageRecorderBase
from loto.coverage.ledger_recorder_events import CoverageRecorderEventsMixin
from loto.coverage.ledger_types import (
    CoverageLedgerBlocked,
    CoverageLedgerCloseResult,
)
from loto.data_access_ledger import AccessDecision, build_ledger, validate_ledger


class CoverageLedgerRecorder(CoverageRecorderEventsMixin, CoverageRecorderBase):
    """Runtime recorder for coverage build and bounded search lanes."""

    def close(self) -> CoverageLedgerCloseResult:
        if self._closed:
            raise CoverageLedgerBlocked("recorder is already closed")
        self._closed = True
        for state in self.folds.values():
            if not state.predicted:
                self.mark_gap(f"FOLD_PREDICTION_MISSING:{state.fold_id}")
            if not state.actual_read:
                self.mark_gap(f"FOLD_ACTUAL_READ_MISSING:{state.fold_id}")
            if not state.scored:
                self.mark_gap(f"FOLD_SCORE_MISSING:{state.fold_id}")
        if not self.folds:
            self.mark_gap("NO_INSTRUMENTED_FOLDS")

        ledger = build_ledger(
            run_id=self.run_id,
            created_at=self.created_at,
            events=self.events,
            expected_seeds=self.expected_seeds,
        )
        validation = validate_ledger(ledger)
        gaps = list(self.coverage_gaps)
        gaps.extend(item.code.value for item in validation.findings)
        gaps = list(dict.fromkeys(gaps))
        status = "PASS" if not gaps and validation.status is AccessDecision.PASS else "BLOCKED"
        ledger_path = self.output_dir / "coverage_data_access_ledger.json"
        validation_path = self.output_dir / "coverage_data_access_validation.json"
        report_path = self.output_dir / "coverage_data_access_report.json"
        atomic_write_json(ledger_path, ledger.model_dump(mode="json"))
        atomic_write_json(
            validation_path,
            validation.model_dump(mode="json"),
        )
        atomic_write_json(
            report_path,
            {
                "status": status,
                "run_id": self.run_id,
                "ledger_sha256": ledger.ledger_sha256,
                "verified_events": validation.verified_event_count,
                "coverage_gaps": gaps,
                "runtime_interception": True,
                "protected_test_evaluated": False,
                "protected_test_materialized": False,
                "protected_test_rows": [
                    self.evidence.protected_test_start,
                    self.evidence.protected_test_end,
                ],
                "memory_sandbox": False,
            },
        )
        result = CoverageLedgerCloseResult(
            status=status,
            run_id=self.run_id,
            ledger_path=ledger_path,
            validation_path=validation_path,
            report_path=report_path,
            ledger_sha256=ledger.ledger_sha256,
            verified_events=validation.verified_event_count,
            coverage_gaps=tuple(gaps),
        )
        if status != "PASS":
            raise CoverageLedgerBlocked("coverage ledger blocked: " + ", ".join(gaps))
        return result
