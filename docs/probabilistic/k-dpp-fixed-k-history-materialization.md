# k-DPP fixed-k approved-history materialization

## Status

`PARTIALLY_VERIFIED / MATERIALIZER_IMPLEMENTED / REAL_EXPORT_PENDING / HUMAN_APPROVAL_PENDING / CPU_FORMAL_PENDING`

This phase converts only a previously verified and human-approved five-game raw-history handoff into the exact four-file Train-only bundle required by the private k-DPP target-host gate. It does not connect to PostgreSQL, reopen Parquet, execute the model, or claim forecasting accuracy.

## Reused repository boundary

The source must be the immutable output produced by Toto raw-history PRs #104 and #106:

```text
numbers3.json
numbers4.json
miniloto.json
loto6.json
loto7.json
history_verification.json
history_approval.json
HISTORY_HANDOFF.json
```

This reuses the existing read-only PostgreSQL export and independent JSON/Parquet verification instead of creating another database extractor. The materializer verifies the exact file set, every copied-file SHA-256, reviewer identity, approval scope, database/export binding, five-game coverage, row counts, JSON hashes, and Parquet hashes retained in the verification evidence.

## Deterministic conversion

For Numbers3 and Numbers4, one position-local lane is produced per invocation. Item IDs are `n<position>:0` through `n<position>:9`, with `k=1`.

For MiniLoto, Loto6, and Loto7, one unordered fixed-cardinality indicator row is produced per draw:

- MiniLoto: 31 items, k=5;
- Loto6: 43 items, k=6;
- Loto7: 37 items, k=7.

All approved rows are used as Train. `forecast_origin` is the next one-based draw ordinal after the final included row. The converter does not accept an earlier cutoff and therefore does not inspect later actuals while claiming an earlier forecast origin.

`training.npz` is written with fixed ZIP metadata and sorted arrays, so the same approved handoff and lane produce identical bytes.

## Output bundle

```text
history_manifest.json
item_ids.json
training.npz
SHA256SUMS
```

The manifest binds the original read-only query hash, database snapshot hash, complete approved-handoff tree SHA-256, exact row range, geometry, output hashes, and no-future-actual/Holdout/Prospective declarations.

## Approval lifecycle

```text
materialize
  -> pending
  -> independent human review
  -> approve
  -> verify
  -> PR #117 prepare/run/verify
```

Approval requires the literal token `APPROVE-KDPP-HISTORY-BUNDLE`, a named reviewer, UTC review time, and nine explicit confirmations covering source read-only status, Train-only scope, draw order, row count, geometry, cutoff, and absence of future actuals, Holdout, and Prospective rows.

Pending and approved records must remain outside the four-file immutable bundle.

## Example

```bash
python scripts/materialize_kdpp_fixed_k_history.py materialize \
  --source-handoff /absolute/materialized-approved-history \
  --output-dir /absolute/kdpp-loto7-history \
  --game loto7

python scripts/materialize_kdpp_fixed_k_history.py pending \
  --bundle /absolute/kdpp-loto7-history \
  --output /absolute/kdpp-loto7-history.pending.json

python scripts/materialize_kdpp_fixed_k_history.py approve \
  --bundle /absolute/kdpp-loto7-history \
  --pending /absolute/kdpp-loto7-history.pending.json \
  --output /absolute/kdpp-loto7-history.approved.json \
  --reviewer REVIEWER \
  --reviewed-at-utc 2026-08-06T04:30:00Z \
  --approval-token APPROVE-KDPP-HISTORY-BUNDLE \
  --confirm-source-read-only \
  --confirm-train-only \
  --confirm-draw-order \
  --confirm-row-count \
  --confirm-game-geometry \
  --confirm-cutoff \
  --confirm-no-future-actuals \
  --confirm-no-holdout \
  --confirm-no-prospective

python scripts/materialize_kdpp_fixed_k_history.py verify \
  --bundle /absolute/kdpp-loto7-history \
  --approval /absolute/kdpp-loto7-history.approved.json
```

## Non-claims

- real PostgreSQL export: not executed;
- real PyArrow verification: not executed;
- real human approval: not performed;
- real k-DPP CPU process pair: not executed;
- CPU_FORMAL: not established;
- public registration: blocked;
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE: not executed or measured.
