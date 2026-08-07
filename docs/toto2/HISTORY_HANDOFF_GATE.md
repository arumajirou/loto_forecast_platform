# Toto 2.0 4M verified-history handoff gate

Status: `IMPLEMENTED / DEPENDENCY_LIGHT_VERIFIED / REAL_EXPORT_APPROVAL_PENDING`.

## Purpose

The target-host preparation command previously accepted any directory containing five history JSON
files. An operator could verify a raw-history export and then accidentally or deliberately point
`prepare` at different bytes. This gate binds request generation to one independently verified
export, one explicit human approval, and the exact SHA-256 identity of every game JSON and Parquet
file.

The gate does not approve data automatically and does not execute Toto inference.

## Bound evidence

The approval record is tied to:

- the absolute immutable export directory;
- `EXPORT_MANIFEST.json` SHA-256;
- `SHA256SUMS` SHA-256;
- `RAW_QUERY.sql` SHA-256;
- `DATABASE_SNAPSHOT.json` SHA-256;
- the independent verification JSON SHA-256;
- JSON and Parquet SHA-256 for all five games;
- draw counts, first and last dates, position counts, and observed ranges;
- `future_actuals_used=false` and `raw_data_modified=false`.

Any byte change requires a new independent verification and a new approval.

## 1. Create a pending approval record

Run after the raw-history exporter and independent verifier pass:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

uv run --extra postgres python scripts/manage_toto2_4m_history_approval.py \
  create-pending \
  --export-root "$HISTORY_EXPORT_ROOT" \
  --verification "$HISTORY_VERIFICATION" \
  --output "$WORK_ROOT/history_approval.pending.json"
```

The pending record contains exact hashes but remains `PENDING`. It cannot open request generation.

## 2. Human review

Inspect at minimum:

- `RAW_QUERY.sql` and its `ts_type='raw'` restriction;
- `DATABASE_SNAPSHOT.json` read-only and repeatable-read facts;
- per-game row and draw counts;
- first and last `ds` cutoffs;
- observed value ranges and position counts;
- JSON and Parquet equality reported by the independent verifier;
- the absence of future actuals and source-table modification.

Do not approve solely because the exporter or verifier printed `PASS`.

## 3. Create the approved record

After the named reviewer completes those checks:

```bash
uv run --extra postgres python scripts/manage_toto2_4m_history_approval.py \
  approve \
  --export-root "$HISTORY_EXPORT_ROOT" \
  --verification "$HISTORY_VERIFICATION" \
  --pending "$WORK_ROOT/history_approval.pending.json" \
  --output "$WORK_ROOT/history_approval.approved.json" \
  --reviewer "<human reviewer>" \
  --reviewed-at "<UTC timestamp ending in Z>" \
  --approval-token APPROVE-TOTO2-HISTORY-EXPORT \
  --confirm-source-query \
  --confirm-database-snapshot \
  --confirm-row-counts \
  --confirm-cutoff-dates \
  --confirm-position-ranges
```

The token is an accidental-execution guard, not a secret and not a substitute for review.

## 4. Prepare the runtime matrix

The formal wrapper now requires all three history inputs:

```bash
export HISTORY_EXPORT_ROOT=/absolute/path/to/immutable-export
export HISTORY_VERIFICATION=/absolute/path/to/raw-history-verification.json
export HISTORY_APPROVAL=/absolute/path/to/history_approval.approved.json
export SNAPSHOT=/absolute/path/to/pinned-snapshot
export EXPECTED_HEAD=<exact-clean-git-head>
export WORK_ROOT=/absolute/path/to/new-work-root

bash environments/toto2-4m-py312/target-host-certification.sh prepare
```

Direct `HISTORY_ROOT` input is no longer accepted. Before request generation, the preparation
command:

1. reruns the independent export verifier;
2. compares the saved verification with the fresh result;
3. validates every approval field and review confirmation;
4. recomputes every bound SHA-256;
5. copies only the five approved JSON files plus verification and approval evidence into a new
   `approved-history` directory;
6. rechecks the source export after copying;
7. atomically publishes the copied directory;
8. generates all 90 requests from the copied, hash-verified JSON files.

`PREPARATION_RESULT.json` records the approval, verification, and export-manifest hashes and the
named reviewer. The matrix remains blocked until the separate dependency-lock review is also
approved.

## Fail-closed conditions

Preparation fails for a pending approval, missing confirmation, wrong approval token, unknown
approval field, invalid UTC timestamp, changed verification, changed manifest, changed JSON or
Parquet file,
changed query or database snapshot, path relocation without re-verification, source mutation during
copy, existing destination, or approval evidence stored inside the immutable export directory.

## Verification boundary

Dependency-light tests validate schema strictness, hash binding, tamper rejection, explicit
approval, and atomic materialization with synthetic bytes. They do not prove a real PostgreSQL
export, PyArrow serialization, human review, target-host package installation, snapshot load,
CPU/CUDA inference, GPU evidence, runtime-matrix completion, or forecasting accuracy.
