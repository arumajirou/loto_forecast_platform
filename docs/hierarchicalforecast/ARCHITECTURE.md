# HierarchicalForecast architecture

## Overview

The component is divided into three fail-closed layers so that upstream runtime execution,
formal-case evaluation, and evidence publication remain independently verifiable.

```text
Caller / console script
        |
        v
package_certification.main
        |
        +--> RuntimeCertificationConfig validation
        |
        +--> runtime_certification.run_certification
        |        |
        |        +--> deterministic game inputs
        |        +--> 40-case matrix
        |        +--> hierarchy adapter
        |        +--> runtime artifacts + SHA256SUMS
        |
        +--> verify_run_directory
        +--> build temporary deterministic ZIP
        +--> verify temporary ZIP
        +--> immutable publish or identical reuse
        +--> verify final ZIP + sidecar
```

## Adapter layer

Location:

```text
src/loto/reconciliation/hierarchy.py
```

Responsibilities:

- map the registered method name to the upstream class
- preserve safe constructor defaults
- filter arguments against the installed method signature
- convert `S` to CSR for sparse implementations
- require paired in-sample arrays when upstream tags declare that requirement
- reject strict-tree methods for the grouped project hierarchy
- execute `fit_predict()`
- normalize the returned `mean` output
- validate expected shape, finite values, and coherence
- return structured fail-closed evidence

The adapter does not decide formal campaign success. It reports one method invocation result.

## Runtime-certification layer

Location:

```text
src/loto/reconciliation/runtime_certification.py
```

Responsibilities:

- validate the formal configuration with Pydantic
- inspect import, module version, distribution version, and module location
- generate deterministic per-game inputs from seed `1`
- share the same game input fairly across all methods
- execute or reject every method according to the formal matrix
- continue after individual method exceptions
- capture warnings, durations, traceback evidence, source hashes, and environment evidence
- aggregate expected, executed, passed, and failed counts
- assign the formal runtime status
- atomically write the primary artifacts and portable checksums

This layer produces evidence even when the optional dependency is missing or formal execution
fails. It does not package or publish the ZIP.

## Package-certification layer

Location:

```text
src/loto/reconciliation/package_certification.py
```

Responsibilities:

- invoke runtime certification through the registered console command
- distinguish configuration, harness, and packaging phases
- verify required artifact coverage and SHA256SUMS
- verify artifact-manifest sizes and hashes
- verify Run ID, run directory, and certification status consistency
- build canonical package-manifest bytes
- create a temporary deterministic ZIP
- reject unsafe paths, duplicates, unexpected members, and metadata divergence
- verify the temporary ZIP before final publication
- reuse an identical existing package without replacement
- reject and preserve any differing ZIP or sidecar
- write and verify the ZIP SHA-256 sidecar

## Data flow

### Input flow

1. CLI arguments are parsed.
2. Pydantic validates games, seed, horizon, in-sample size, expected version, and tolerance.
3. A unique Run ID and run directory are created.
4. Deterministic arrays are generated per game.
5. Each method receives the same game-level inputs under the same formal configuration.

### Execution flow

1. Adapter compatibility checks occur before upstream construction.
2. Executable methods call the real `fit_predict()` path.
3. Sparse methods receive CSR matrices.
4. ERM receives paired in-sample actual and fitted matrices.
5. Results are validated and converted to evidence records.
6. One case failure does not abort the remaining matrix.

### Evidence flow

1. Runtime JSON artifacts are written atomically.
2. Artifact manifest and SHA256SUMS bind the runtime evidence.
3. The packager re-verifies all source evidence.
4. A temporary ZIP is produced with fixed member metadata and order.
5. The temporary ZIP is verified before publication.
6. Final ZIP and sidecar become immutable outputs for the Run ID.

## Trust boundaries

### Upstream package boundary

The installed HierarchicalForecast package is external. Runtime certification records exact module
and distribution evidence and refuses version ambiguity.

### File-system boundary

Runtime artifacts and packages are treated as untrusted until all recorded sizes, hashes, paths,
and Run IDs are verified.

### GitHub Actions boundary

GitHub-hosted CI is external verification infrastructure. A zero-step failed job is neither code
failure evidence nor passing CI evidence. Issue #61 tracks this boundary.

## Failure isolation

| Layer | Failure status | Evidence behavior |
|---|---|---|
| configuration | `INVALID_CONFIGURATION` | structured error; no formal success |
| certification harness | `FAILED_CERTIFICATION_HARNESS` | partial context retained when available |
| dependency/version/runtime | exit-2 formal status | complete runtime evidence packaged when valid |
| package integrity | `FAILED_PACKAGING` | source evidence preserved; mismatched outputs not overwritten |

## Device architecture

Reconciliation is classified as CPU-only for this component. GPU PID, VRAM, and CPU fallback are
recorded as `NOT_APPLICABLE`, not inferred as successful GPU execution.

## Extension points

Future changes may add:

- new registered reconcilers with explicit defaults and tests
- alternative compatible hierarchy definitions
- additional formal games
- versioned artifact schemas
- external artifact storage or MLflow registration

Any extension must preserve deterministic input sharing, fail-closed status semantics, immutable
raw evidence, and the promotion gates defined in `REQUIREMENTS.md`.
