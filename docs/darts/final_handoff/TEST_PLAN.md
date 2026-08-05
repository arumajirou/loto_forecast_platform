# Test plan

## Completed focused contract tests

P1-P12 documented focused runs total 108 passing tests. The final handoff package adds 10
passing tests for required document names, checksum generation, missing/unexpected files,
tamper detection, deterministic ZIP bytes, normalized timestamps and modes, archive
corruption, stale checksums, and output-path isolation.

These are incremental focused runs and not one combined 118-test certification run.

## Static gates

- Python compileall;
- Python AST parsing;
- YAML and JSON parsing;
- no source or test line over 100 characters;
- Pydantic strict-schema rejection;
- canonical SHA-256 stability and tamper sensitivity.

## Pending real-runtime tests

1. Resolve pinned notorch and torch environments for Darts 0.46.1.
2. Pin immutable Foundation revisions and local weight manifests.
3. Execute all eight P12 provider tracks with identical data, folds, seeds, lags, covariates,
   horizon, and Train-only fitting.
4. Verify wrapper and standalone prediction parity where strict parity is expected.
5. Capture complete CPU/GPU process and memory evidence.
6. Run process-boundary save/load, checkpoint, weights, and cross-device replay.
7. Evaluate OOF, Holdout, and sealed Prospective predictions.
8. Compare all required baselines and issue a champion or `NO_CHAMPION` decision.
9. Run Ruff, mypy, focused pytest, then full pytest and GitHub CI.
10. Regenerate this handoff package with the final verified run IDs and hashes.
