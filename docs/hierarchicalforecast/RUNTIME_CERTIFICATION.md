# HierarchicalForecast runtime certification

This command certifies the installed `hierarchicalforecast==1.5.1` runtime. It is a
runtime and integration check, not a forecasting-accuracy experiment.

## Run

```bash
uv sync --extra full
uv run python -m loto.reconciliation.runtime_certification
```

The default run uses seed `1` and executes the same deterministic synthetic input for every
reconciler within each select-family game:

- `mini`
- `loto6`
- `loto7`
- `bingo5`

A narrower diagnostic run is available without changing the formal default:

```bash
uv run python -m loto.reconciliation.runtime_certification \
  --games loto7 \
  --horizon 4 \
  --insample-size 32 \
  --coherence-tolerance 1e-8
```

## Formal matrix

The command checks all ten registered upstream classes.

| Expected state | Reconciler |
|---|---|
| Executes and returns a finite coherent result | `BottomUp`, `BottomUpSparse`, `MinTrace`, `MinTraceSparse`, `OptimalCombination`, `ERM` |
| Rejected before execution for the grouped parity/decade hierarchy | `TopDown`, `TopDownSparse`, `MiddleOut`, `MiddleOutSparse` |

`ERM` receives paired synthetic in-sample actual and fitted arrays. Sparse methods must pass
through the adapter's CSR path. Every executable method must report the exact imported package
version, `actual_execution=true`, the expected output shape, finite values, and coherence within
tolerance.

## Status and exit code

| Status | Exit | Meaning |
|---|---:|---|
| `VERIFIED` | 0 | Exact version and every formal case passed |
| `BLOCKED_DEPENDENCY` | 2 | The optional package could not be imported |
| `FAILED_VERSION_MISMATCH` | 2 | Distribution/module version evidence is inconsistent or differs from `1.5.1` |
| `FAILED_RUNTIME` | 2 | At least one method returned an unexpected status, shape, non-finite value, incoherence, or exception |

A method exception does not terminate the matrix. The harness records the exception and
traceback, continues the remaining cases, and returns `FAILED_RUNTIME`.

## Artifacts

Each run creates
`artifacts/hierarchicalforecast-runtime/hierarchicalforecast-runtime-<UTC>-<PID>/` with:

- `RUNTIME_CERTIFICATION.json`
- `METHOD_RESULTS.json`
- `INPUT_EVIDENCE.json`
- `ARTIFACT_MANIFEST.json`
- `SHA256SUMS`

The evidence records the run ID, UTC timestamps, validated configuration and hash, synthetic
input data hash, Git commit, source-code hashes, package versions, process ID, CPU-only device
boundary, per-method duration and warnings, output hashes, output shape, finite checks, and
coherence checks.

Verify the package after the run:

```bash
cd artifacts/hierarchicalforecast-runtime/<run-id>
sha256sum -c SHA256SUMS
```

## Certification boundary

This command does **not** claim an improvement in Hit@±1, MAE, MSE, RMSE, Holdout, or
Prospective performance. It only proves that the installed reconciliation runtime loads,
receives the expected inputs, executes where applicable, and returns structurally valid coherent
outputs. HierarchicalForecast reconciliation is classified as CPU-only here; GPU PID, VRAM, and
CPU fallback are explicitly `NOT_APPLICABLE` rather than inferred as successful GPU evidence.
