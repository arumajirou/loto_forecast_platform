# Data Contract — Windows-only execution

## Raw-data rule

Raw source data is immutable evidence. Do not overwrite it in place and do not silently regenerate a missing frozen snapshot from a live database.

## Current Timer Base 84M development snapshot

Historical protocol work identified a frozen development snapshot with expected identity:

```text
data_snapshot_sha256=99c6a9c7fc2c9ce5b5f1b8351841c5ead1aeb48f99e6846c289988af56896053
snapshot_scope=development_only
holdout_actual_values_opened=false
prospective_actual_values_opened=false
```

The current repository does not contain evidence sufficient to claim that this snapshot is already present on the Windows host. Before formal OOF, locate or transfer the exact snapshot and verify the expected SHA-256. If the hash differs, stop.

## Game identity rule

MiniLoto requires an explicit physical/logical mapping:

```text
physical_db_id=mini
logical_platform_id=miniloto
```

SQL filtering must use the physical identifier where required, while exported platform records use the logical identifier. The mapping must remain explicit in snapshot/database evidence.

## Chronology rule

For each formal OOF target:

- training/context rows must have `draw_no < target_draw_no`;
- expected development draws must be contiguous according to the frozen split/target inventory;
- target actual must not be included in context;
- prediction sealing must complete before target actual read;
- target game/draw/date identity must be verified after prediction generation and before scoring.

## Split rule

Train, Validation, Holdout, and Prospective are chronological partitions. Scalers, encoders, feature selection, and hyperparameter tuning must be fitted within Train-only boundaries.

## Missing/duplicate/order checks

Formal input validation must detect and reject:

- duplicate draw/position records;
- incomplete draws;
- missing required rows;
- out-of-order chronology;
- future-information columns or target leakage;
- non-finite values;
- invalid game geometry;
- snapshot identity drift.

## Protected data rule

Holdout and Prospective actuals remain closed during the current OOF campaign. Any unexpected opening invalidates the current scientific gate and must be recorded as a stop condition.