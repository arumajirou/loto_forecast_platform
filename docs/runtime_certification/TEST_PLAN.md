# Runtime Certification SDK Foundation Test Plan

## Scope

Tests use a fake provider and injected executor. They do not import Chronos, TimesFM, Uni2TS, TiRex,
Toto, Sundial, TabPFN, NeuralForecast, Merlion or StatsForecast, and they do not require CUDA.

## Contract tests

1. Reject unknown fields and strict-type coercion.
2. Verify canonical request SHA-256.
3. Verify injected package-version metadata and package artifact SHA-256.
4. Reject snapshot revision, containment, size, hash and symlink violations.
5. Validate exact output shape and finite values.
6. Validate quantile monotonicity on a non-leading quantile axis.
7. Require distinct provider PIDs for replay.
8. Accept only bounded non-exact replay differences.
9. Fail on timeout and non-zero process exit.
10. Exercise the complete two-process flow through an injected fake executor.

## Evidence-origin and process-binding tests

1. Real CPU evidence may produce `RUNTIME_CERTIFIED` with profile `CPU_SMOKE`.
2. Complete synthetic CUDA evidence remains `PARTIALLY_VERIFIED` with profile `GPU_FORMAL`.
3. Synthetic evidence cannot be relabelled as real runtime certification.
4. Device/report origin mismatch fails closed.
5. Runtime success retains `accuracy_status=NOT_EVALUATED`.
6. Real evidence requires an observed provider process PID.
7. Execution PID and device-evidence provider PID must match.
8. An observation loader cannot replace executor-owned process evidence.
9. The real subprocess executor records the started provider PID.

## Artifact tests

1. Build deterministic artifact inventory.
2. Write and verify complete `SHA256SUMS`.
3. Detect mutation after sealing.
4. Produce byte-identical evidence ZIPs from identical input trees.
5. Verify the adjacent ZIP SHA-256 sidecar.
6. Reject traversal and symlink ZIP members.
7. Reject control characters in artifact paths before line-based manifest generation.
8. Reject control characters in ZIP member names.

## Validation order

During implementation:

```text
compile new SDK and focused tests
→ run focused pytest
→ run line-length and AST checks
→ run Ruff and mypy only when available
```

Full repository pytest and GitHub Actions are final integration gates and must not be represented as
PASS when unavailable or when a workflow fails before steps are created.

## Future migration tests

Each provider migration PR must add parity fixtures that feed the same provider evidence to its
legacy certifier and common adapter. Differences in status, hashes, device evidence, replay or artifact
inventory block migration. Real GPU tests remain target-host-only and cannot be replaced by fake
fixtures.
