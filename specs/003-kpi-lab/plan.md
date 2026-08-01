# Implementation Plan: KPI Lab

## Scope

Integrate the model-free reference arm, model arm, cost-normalized KPI, sequential
e-process, negative controls, sealed evaluation window, append-only ledger, and optional
CP-SAT certificate without weakening the statistical or dependency boundaries.

## Technical decisions

1. `GameGeometry` remains the only source of lottery geometry.
2. Arm A is always executed before Arm B.
3. Coverage is not interpreted as a prize probability or expected return.
4. Optional solvers fail closed with `SolverUnavailable`; no implicit algorithm fallback.
5. Search and sealed evaluation windows are represented by different state transitions.
6. Every experiment and termination reason is appended to the hash-chained ledger.
7. External LLM proposals are schema-limited and cannot alter KPI, alpha, holdout, or budget.

## Verification layers

- Hermetic unit tests: no GPU, network, database, MLflow, or optional solver.
- Optional solver test: executed only when OR-Tools is installed.
- CLI smoke test: sample config, bounded budget, temporary output directory.
- Integration test in target repository after installation.

## Rollback

The installer records SHA-256 values and copies replaced files into a timestamped backup.
Rollback restores only files listed in the generated manifest and refuses unknown paths.
