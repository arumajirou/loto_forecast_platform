# Data Access Ledger v1

Status: `IMPLEMENTED / STATIC_CONTRACT_ONLY / NOT_RUNTIME_WIRED`

Data Access Ledger v1 records each material data read, fit, transform, join, aggregate, label,
score, and write as a strict, repository-local evidence record. It is intentionally independent
from model providers, runtime certification, prediction locking, actual-source ingestion, model
registry, promotion, configuration, API, and PR-integration workflows.

## Guarantees

The v1 validator fails closed when it finds:

- fitting or fitting a transformer outside the `train` split;
- predictive feature, fit, selection, tuning, evaluation, or scoring access without a prediction
  cutoff or dataset-availability evidence;
- a data-consuming event without a bounded end timestamp;
- a read window, dataset availability timestamp, column-known timestamp, or dependency after the
  consumer's prediction cutoff;
- holdout use during feature construction, fitting, model selection, or hyperparameter tuning;
- prospective or actual data use before scoring/audit/ingestion;
- current target or actual columns used during feature construction;
- unbounded column temporal scope;
- unknown, non-causal, or later-split dependencies;
- naive datetimes, while normalizing accepted timezone-aware values to UTC.

The AST scanner identifies selected read, write, fit, fit-transform, and join calls that do not have
a matching ledger event at the same repository-relative file and source line. It distinguishes
literal read/write modes for `open()` and covers common pathlib, pandas, and polars writes. The
scanner is a static control: a clean result is evidence that declared calls are covered, not proof
that no leakage exists. Dynamic SQL, reflection, generated code, C extensions, dynamically computed
open modes, and unsupported I/O APIs remain outside v1.

## Minimal declaration

```python
from datetime import UTC, datetime

from loto.data_access_ledger import (
    AccessMode,
    AccessPurpose,
    CodeLocation,
    ColumnAccess,
    ColumnRole,
    DataAccessEvent,
    DataAccessLedger,
    SplitRole,
    TemporalScope,
    TimeBoundary,
    validate_ledger,
)

cutoff = datetime(2026, 8, 6, tzinfo=UTC)
ledger = DataAccessLedger(
    ledger_id="numbers4-feature-build-v1",
    generated_at=cutoff,
    code_revision="0" * 40,
    events=[
        DataAccessEvent(
            event_id="read-train-history",
            process_id="numbers4-feature-build",
            sequence=1,
            mode=AccessMode.READ,
            purpose=AccessPurpose.FEATURE_BUILD,
            split=SplitRole.TRAIN,
            dataset="dataset.numbers4_raw",
            columns=[
                ColumnAccess(
                    name="d1_lag_1",
                    role=ColumnRole.FEATURE,
                    temporal_scope=TemporalScope.PAST_ONLY,
                    lag=1,
                )
            ],
            boundary=TimeBoundary(
                end=cutoff,
                prediction_cutoff=cutoff,
                available_at=cutoff,
            ),
            location=CodeLocation(path="src/pipeline/features.py", line=42),
        )
    ],
)
assert validate_ledger(ledger).passed
```

## Schema rules

- `schema_version` is exactly `1.0.0`.
- Unknown fields are rejected at every model boundary.
- Events are ordered by `(sequence, event_id)` and event IDs are unique.
- All accepted datetimes are timezone-aware and canonicalized to UTC.
- SHA-256 evidence fields, when present, are lowercase 64-character hexadecimal strings.
- Code locations are repository-relative POSIX paths and cannot contain `..`.
- Read-like events must enumerate accessed columns.

## Verification

Focused local gate:

```bash
python -m ruff format --check src/loto/data_access_ledger tests/data_access_ledger
python -m ruff check src/loto/data_access_ledger tests/data_access_ledger
python -m compileall -q src/loto/data_access_ledger tests/data_access_ledger
PYTHONPATH=src python -m pytest -q tests/data_access_ledger
```

The focused suite currently contains 11 tests. No runtime integration or production certification is
claimed by this PR.
