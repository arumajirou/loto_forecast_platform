# Toto 2.0 4M immutable raw-history export

Status: `IMPLEMENTED / DEPENDENCY_LIGHT_VERIFIED / REAL_DATABASE_EXPORT_PENDING`.

## Source contract

The exporter reads only these columns from `dataset.loto_y_ts_unified`:

- `loto`;
- `ds`;
- `unique_id`;
- `ts_type`;
- `y`.

Only `ts_type='raw'` and the five formal games are selected. The transaction is explicitly
`REPEATABLE READ READ ONLY`. No `INSERT`, `UPDATE`, `DELETE`, DDL, temporary table, or source-file
write is performed.

## Output contract

Each game produces:

- `<game>.json`: the strict history format consumed by the target-host request factory;
- `<game>.parquet`: an audit table retaining `ds`, ordinal `draw_no`, and all positions.

`draw_no` is a one-based ordinal over sorted `ds`; it is not claimed to be an official lottery draw
identifier. Original dates remain in Parquet and the export manifest.

The bundle also contains the exact SQL, database snapshot evidence, an export manifest, and
`SHA256SUMS`. Existing output directories are never overwritten.

## Data-quality gates

The exporter rejects:

- games other than the exact five-game set;
- missing required source columns;
- unsupported series identifiers;
- duplicate `(ds, position)` keys;
- incomplete draws;
- fewer than 512 complete draws;
- null, non-numeric, non-finite, non-integer, or out-of-domain values;
- non-increasing MiniLoto, Loto6, or Loto7 positions.

## Commands

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -a
source "$HOME/.config/loto/runtime.env"
set +a

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$PWD/artifacts/toto2-4m-raw-history/$RUN_ID"

uv run --extra postgres python scripts/export_toto2_4m_raw_history.py \
  --output-root "$OUT"

uv run python scripts/verify_toto2_4m_raw_history_export.py \
  --export-root "$OUT" \
  --verification-output "${OUT}.verification.json"
```

A successful export is not model runtime or forecasting-accuracy evidence. The independently
verified JSON files become inputs to PR #102's `prepare` phase.
