# Requirements

## Functional requirements

1. Record immutable dataset identity, SHA-256, role, row range, observed-time range, availability,
   forecast origin, targets/actual flags, and source immutability.
2. Record state identity, kind, SHA-256, producing fit event, fitted dataset provenance, run
   binding,
   optional authorized reuse runs, and optional HPO fold hash.
3. Record event order, stage, operation, timestamp, actor, slices, states, parents, forecast
   identity,
   OOF fold/seed, operator actual assertion, and notes.
4. Validate event identity, sequence, timestamp order, parent DAG, dataset hash consistency, and
   ledger
   tamper evidence.
5. Enforce Train-only fit/scaler/encoder/feature-selection scope.
6. Enforce chronological Train-only tuning folds and fold-hash evidence.
7. Enforce prior, exact, Train-fitted state provenance for Transform/Predict consumers.
8. Enforce chronological OOF fit/predict order and identical training scope across seeds.
9. Enforce Holdout restrictions and Prospective `PREDICT -> LOCK -> READ_ACTUALS -> SCORE` order.
10. Reject fit/tune/calibrate/predict inputs that became available after forecast origin.
11. Provide canonical UTF-8 JSON SHA-256 and a dependency-light `python -m` CLI.
12. Produce machine-readable findings without using notes or `actuals_known` as certification
    evidence.

## Quality requirements

All contracts use Pydantic v2 with `extra="forbid"`, `strict=True`, `allow_inf_nan=False`, and
`validate_assignment=True`. Datetimes must be timezone-aware UTC. SHA-256 values are lowercase
64-character hexadecimal strings. No new dependency, root entrypoint, workflow, or prohibited module
is introduced.
