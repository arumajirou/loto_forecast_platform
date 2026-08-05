# HierarchicalForecast specification

## Component boundary

PR #48 defines three related layers:

1. reconciliation adapter
2. runtime-certification harness
3. immutable evidence packager

The adapter executes upstream reconciliation. The harness constructs and evaluates a deterministic
formal matrix. The packager verifies and seals the resulting evidence.

## Public operational command

```bash
uv sync --extra full
uv run loto-hierarchicalforecast-certify
```

Registered entry point:

```text
loto-hierarchicalforecast-certify = loto.reconciliation.package_certification:main
```

Runtime-only diagnostic command:

```bash
uv run python -m loto.reconciliation.runtime_certification
```

## Adapter interface

The adapter accepts:

- upstream method name
- summing matrix `S`
- base forecasts `y_hat`
- optional in-sample actual matrix
- optional in-sample fitted matrix
- optional constructor method options
- coherence tolerance

The adapter returns structured status and evidence. `VERIFIED` is reserved for successful actual
execution followed by output validation.

## Supported upstream classes

| Class | Default option | Grouped hierarchy behavior |
|---|---|---|
| `BottomUp` | none | execute |
| `BottomUpSparse` | none | execute through CSR |
| `TopDown` | `method=forecast_proportions` | reject as strict-tree |
| `TopDownSparse` | `method=forecast_proportions` | reject as strict-tree |
| `MiddleOut` | `top_down_method=forecast_proportions` | reject as strict-tree |
| `MiddleOutSparse` | `top_down_method=forecast_proportions` | reject as strict-tree |
| `MinTrace` | `method=ols` | execute |
| `MinTraceSparse` | `method=ols` | execute through CSR |
| `OptimalCombination` | `method=ols` | execute |
| `ERM` | `method=closed` | execute with paired in-sample arrays |

`MiddleOut` variants additionally require a configured middle level when used with a compatible
strict hierarchy.

## Formal runtime configuration

| Field | Default |
|---|---|
| expected version | `1.5.1` |
| seed | `1` |
| games | `mini,loto6,loto7,bingo5` |
| horizon | `4` |
| in-sample size | `32` |
| coherence tolerance | `1e-8` |
| output root | `artifacts/hierarchicalforecast-runtime` |

The formal matrix is 4 games × 10 methods = 40 cases.

## Case-state specification

Expected executable methods:

- `BottomUp`
- `BottomUpSparse`
- `MinTrace`
- `MinTraceSparse`
- `OptimalCombination`
- `ERM`

Expected grouped-hierarchy rejections:

- `TopDown`
- `TopDownSparse`
- `MiddleOut`
- `MiddleOutSparse`

A formal case passes only when its observed state equals its expected state and all executable-case
validation evidence is true.

## Runtime artifact specification

Each Run ID directory contains:

```text
RUNTIME_CERTIFICATION.json
METHOD_RESULTS.json
INPUT_EVIDENCE.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

### `RUNTIME_CERTIFICATION.json`

Contains overall status, formal success, Run ID, run directory, configuration, package evidence,
runtime environment, source hashes, dependency evidence, and summary counts.

### `METHOD_RESULTS.json`

Contains all 40 case records, including expected status, observed status, execution evidence,
shape, finite and coherence checks, warnings, duration, hashes, and exceptions.

### `INPUT_EVIDENCE.json`

Contains deterministic input evidence per game, including shapes and SHA-256 values rather than
unbounded raw-array duplication.

### `ARTIFACT_MANIFEST.json`

Contains Run ID and byte/hash records for the primary JSON artifacts.

### `SHA256SUMS`

Contains portable SHA-256 rows for all primary runtime artifacts.

## Package specification

Sibling outputs:

```text
<run-id>.zip
<run-id>.zip.sha256
```

ZIP members:

```text
<run-id>/RUNTIME_CERTIFICATION.json
<run-id>/METHOD_RESULTS.json
<run-id>/INPUT_EVIDENCE.json
<run-id>/ARTIFACT_MANIFEST.json
<run-id>/SHA256SUMS
<run-id>/PACKAGE_MANIFEST.json
```

The archive uses deterministic member order and fixed metadata. The package manifest records file
sizes, SHA-256 values, certification status, Run ID, and content-set SHA-256.

## Status and exit specification

| Status | Exit |
|---|---:|
| `VERIFIED` | 0 |
| `BLOCKED_DEPENDENCY` | 2 |
| `FAILED_VERSION_MISMATCH` | 2 |
| `FAILED_RUNTIME` | 2 |
| `INVALID_CONFIGURATION` | 3 |
| `FAILED_CERTIFICATION_HARNESS` | 3 |
| `FAILED_PACKAGING` | 3 |

Exit 2 means a packageable formal certification result exists but must not be promoted. Exit 3
means configuration, harness execution, or evidence integrity prevented a valid packaged result.

## Promotion specification

The branch is eligible to move from Draft only after:

- real installed version 1.5.1 produces 40/40 passing cases
- immutable package verification passes
- Ruff and required static checks pass
- focused and full pytest pass
- GitHub Actions produces real step logs and passing required checks
- the verification report is updated with exact Run ID, ZIP SHA-256, Git commit, package version,
  and CI run identifiers
