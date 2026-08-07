# Research orchestration adapter

Status: `STACKED_ADOPTION / OPT_IN / POST_RUN_RECONCILIATION`

`loto.orchestration.research_ledger_adapter` integrates the Data Access Ledger v1
foundation without editing or monkeypatching `src/loto/orchestration/research.py`.
The existing research runner remains the delegated implementation.

## Safety lane

The adapter accepts only runs where:

- `search.backend == "none"`;
- `runtime.resume == false`;
- `observability.mlflow_uri` is unset;
- the input and output paths are regular, non-symlink paths.

Tuning, resume-artifact reads, and MLflow writes are rejected before the delegated
runner starts because the adapter cannot intercept those internal accesses or stop
MLflow recording after the original runner has begun.

## Evidence

For each successful model/seed/fold/draw, the adapter reconciles:

1. a Train-only walk-forward `FIT_MODEL` event;
2. an OOF `PREDICT` event using a target-free forecast-identity projection;
3. an OOF `READ_ACTUALS` event after prediction.

It writes:

- `data_access_ledger.json`;
- `data_access_validation.json`;
- `data_access_adapter_report.json`.

The source file is hashed before and after execution. Mutation, failed/skipped trial
coverage gaps, data-version disagreement, missing fold evidence, artifact-count
mismatch, or foundation-validator findings block downstream use.

## Non-claims

This adapter performs post-run reconciliation. It is not runtime interception and
cannot prove that an uninstrumented function made no additional access. It therefore
fails closed for lanes whose material access cannot be reconstructed. It does not
perform Holdout evaluation, Prospective prediction locking, Actual Source
verification, registration, promotion, MLflow reconciliation, or runtime/GPU
certification.
