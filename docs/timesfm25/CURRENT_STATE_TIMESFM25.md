# Current State: TimesFM 2.5

Status: `FACT_CHECKED / CONTRACT_V2_IMPLEMENTED / RUNTIME_PARTIALLY_VERIFIED`.

The main branch provider currently hard-codes `n1` through `n7`, requests one step, returns only the first point forecast, discards quantile values, and does not require a checkpoint revision. This package introduces an isolated v2 contract without modifying the shared worker/catalog paths.

## Evidence discrepancy

The old GitHub branch `feat/timesfm-2-5-transformers-runtime-audit-v1` contains a Transformers runtime result marked `BLOCKED` with reason `FIXED_SNAPSHOT_MISSING`. Therefore this PR does not claim that the Transformers lane is GPU-certified. The model identity is pinned and the certification schema is implemented; execution certification remains a later runtime task.
