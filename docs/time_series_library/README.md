# Time-Series-Library provider contract v1

## Status

`PARTIALLY_VERIFIED / REAL_PINNED_DLINEAR_CPU_VERIFIED / FULL_MATRIX_PENDING`

This integration isolates `thuml/Time-Series-Library` at revision
`4e938a1767106324dd753b2a44832bf870a0252e` from the root runtime.

## Source policy

Provider requests default to `source_policy="pinned"`. DLinear fit and load operations
verify the Git blob identities of both the upstream DLinear model and its Autoformer
series-decomposition dependency before execution. A mismatch fails closed.

`source_policy="test_fixture"` exists only for focused contract tests. Its response is
marked `TEST_FIXTURE` and must not be interpreted as upstream runtime certification.

## Included

- fixed upstream provenance;
- isolated CPU dependency lane;
- strict Pydantic request and response schemas;
- draw-sequence `GameGeometry`;
- explicit Train, Validation, Holdout, and Prospective boundaries;
- training materialization containing only Train and Validation rows;
- AST-based model inventory without importing optional dependencies;
- DLinear CPU fit, finite-state, save, process-exit, load, and re-predict contract;
- SHA-256 evidence for checkpoint, input, and predictions;
- fail-closed response status and exit code 2.

## Real runtime result

The PR provider was executed with exact pinned upstream DLinear source files. CPU fit,
save, strict reload in a separate process, and re-prediction passed. Predictions were
bitwise identical with maximum absolute error `0.0`.

The available runtime used Torch 2.10.0 CPU. Resolution and execution of the declared
Torch 2.9.1 isolated environment remain blocked by network and offline-cache limits.

## Provider operations

- `discover`
- `dlinear_fit_save`
- `dlinear_load_predict`
- `verify_roundtrip`

Example request field:

```json
{
  "source_policy": "pinned"
}
```

## Certification boundary

A model listed by discovery is not runtime certified. GPU success additionally requires
parameter, input, output, PID, VRAM, and no-CPU-fallback evidence. Holdout and
Prospective data remain unopened in this increment.
