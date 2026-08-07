"""Coverage research helpers and opt-in Data Access Ledger adoption."""

from loto.coverage.instrumented import (
    EXPECTED_AUTO_RESEARCH_BLOB_SHA,
    EXPECTED_COVERAGE_RUNNER_BLOB_SHA,
    run_auto_research_with_ledger,
    run_coverage_experiment_with_ledger,
)
from loto.coverage.ledger import (
    CoverageDatasetEvidence,
    CoverageLedgerBlocked,
    CoverageLedgerCloseResult,
    CoverageLedgerError,
    CoverageLedgerPreflightError,
    CoverageLedgerRecorder,
)

__all__ = [
    "CoverageDatasetEvidence",
    "CoverageLedgerBlocked",
    "CoverageLedgerCloseResult",
    "CoverageLedgerError",
    "CoverageLedgerPreflightError",
    "CoverageLedgerRecorder",
    "EXPECTED_AUTO_RESEARCH_BLOB_SHA",
    "EXPECTED_COVERAGE_RUNNER_BLOB_SHA",
    "run_auto_research_with_ledger",
    "run_coverage_experiment_with_ledger",
]
