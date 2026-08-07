# HierarchicalForecast requirements

## Purpose

Define the acceptance requirements for the HierarchicalForecast reconciliation adapter, runtime
certification harness, immutable evidence package, and operational handoff introduced by PR #48.

## Functional requirements

### Adapter execution

- The adapter must call the selected upstream reconciler's real `fit_predict()` method.
- Constructor availability alone must never be reported as runtime success.
- All ten registered upstream reconciler class names must be supported by explicit dispatch.
- Sparse reconciler variants must receive the summing matrix through the CSR route.
- Methods declaring `insample=True` must receive paired in-sample actual and fitted matrices.
- Constructor options must be explicit, validated, and passed only when accepted by the installed
  signature.

### Hierarchy compatibility

- The project number hierarchy must be treated as grouped because parity and decade are parallel
  aggregations.
- Strict-tree methods must be rejected before construction for this grouped hierarchy.
- Unsupported hierarchy must not be converted into execution success.

### Output validation

A reconciler may return `VERIFIED` only when all of the following are true:

- actual upstream execution occurred
- returned shape equals the expected hierarchy-by-horizon shape
- every returned value is finite
- coherence satisfies `S @ bottom == reconciled` within the configured tolerance
- imported package version is recorded

### Fail-closed statuses

The adapter must use explicit statuses including:

- `UNAVAILABLE`
- `UNSUPPORTED_HIERARCHY`
- `CONFIGURATION_REQUIRED`
- `CONFIGURATION_ERROR`
- `REQUIRES_INSAMPLE`
- `EXECUTION_FAILED`
- `VALIDATION_FAILED`
- `VERIFIED`

## Runtime-certification requirements

- The formal target version must be exactly `hierarchicalforecast==1.5.1`.
- Module and distribution version evidence must agree.
- Formal seed must default to `1`.
- Formal games must be `mini`, `loto6`, `loto7`, and `bingo5`.
- All ten registered reconciler classes must be evaluated for every game.
- The formal matrix must therefore contain 40 cases.
- Deterministic inputs must be shared fairly across methods within each game.
- One method failure must not prevent remaining cases from being recorded.
- Unexpected exceptions must be retained with traceback evidence.

## Evidence requirements

Every runtime attempt must preserve:

- Run ID
- UTC timestamps
- validated configuration and configuration SHA-256
- deterministic input-data SHA-256
- Git commit and source/code hashes
- imported module and distribution versions
- process and CPU-only device evidence
- per-method status, duration, warning, shape, finite, coherence, and output hash evidence
- complete runtime artifact manifest
- portable `SHA256SUMS`

Raw runtime evidence must not be overwritten.

## Immutable package requirements

- Required runtime artifacts must be verified before packaging.
- A temporary ZIP must be fully verified before final publication.
- ZIP member paths must remain under one Run ID prefix.
- Duplicate names, path traversal, unsafe names, and unexpected members must be rejected.
- ZIP timestamps, Unix file mode, creator system, and storage method must be fixed.
- `PACKAGE_MANIFEST.json` bytes must be canonical and verified exactly.
- Existing identical ZIPs may be reused without replacement.
- Existing differing ZIPs or sidecars must be retained and rejected.
- ZIP SHA-256 must be written to a sidecar only after final archive verification.

## Exit-code requirements

| Exit | Status family | Requirement |
|---:|---|---|
| 0 | `VERIFIED` | Runtime and package both passed |
| 2 | dependency, version, or runtime failure | Evidence retained; never promoted |
| 3 | configuration, harness, or package failure | Structured phase and error retained |

## Verification requirements

Promotion requires:

1. exact installed version `1.5.1`
2. console command exit code `0`
3. certification status `VERIFIED`
4. expected, executed, and passed cases all equal `40`
5. failed cases equal `0`
6. ZIP sidecar verification passes
7. `unzip -t` passes
8. internal `SHA256SUMS` verification passes
9. Ruff and required static checks pass
10. focused and repository-wide pytest pass
11. GitHub Actions produces real steps, logs, and passing required checks

## Non-goals

This component does not claim or evaluate improvement in:

- Hit@±1
- position-level Hit@±1
- all-position Hit@±1
- MAE
- MSE
- RMSE
- Holdout performance
- Prospective performance

## Safety requirements

- No direct push to `main`.
- No force push merely to rewrite history.
- No merge or auto-merge without explicit authorization and completed promotion evidence.
- The PR remains Draft while either real 1.5.1 runtime evidence or functioning CI evidence is
  missing.
