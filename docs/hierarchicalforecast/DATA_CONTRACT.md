# HierarchicalForecast data contract

## Purpose

Define the accepted inputs, produced outputs, invariants, and evidence boundaries for the
HierarchicalForecast reconciliation adapter and formal runtime certification introduced by PR #48.

## Input contract

### Summing matrix `S`

- Represents all hierarchy nodes as rows and bottom-level series as columns.
- Must be two-dimensional.
- Must contain only finite numeric values.
- Must align with the first dimension of base forecasts.
- Sparse reconciler variants receive a CSR representation.
- The project number hierarchy is grouped because parity and decade are parallel aggregations.

### Base forecast matrix `y_hat`

- Shape must be `(n_nodes, horizon)`.
- `n_nodes` must equal the number of rows in `S`.
- `horizon` must be positive.
- Every value must be finite.
- The same deterministic game-level matrix is shared across methods during formal certification.

### In-sample actual matrix

- Required only for methods whose upstream tags declare `insample=True`.
- Shape must be `(n_nodes, insample_size)`.
- Every value must be finite.
- Must be supplied together with the in-sample fitted matrix.

### In-sample fitted matrix

- Required as the pair of the in-sample actual matrix.
- Shape must exactly equal the actual matrix shape.
- Every value must be finite.
- ERM receives the formal paired in-sample arrays.

### Method options

- Must be a mapping of explicit constructor option names to values.
- Unknown or incompatible options must fail closed.
- Options must not silently replace the documented safe defaults.
- Only arguments accepted by the installed method signature may be passed upstream.

### Formal configuration

| Field | Contract |
|---|---|
| `games` | unique subset of `mini`, `loto6`, `loto7`, `bingo5`; formal default is all four |
| `seed` | integer; formal default `1` |
| `horizon` | positive integer; formal default `4` |
| `insample_size` | positive integer; formal default `32` |
| `coherence_tolerance` | finite positive float; formal default `1e-8` |
| `expected_version` | non-empty string; formal value `1.5.1` |
| `output_root` | writable path; raw run directories are not overwritten |

Digit-family games and duplicate game names are rejected by the formal harness.

## Output contract

### Adapter result

The adapter result records at least:

- requested method name
- status
- actual-execution flag
- upstream version when imported
- expected and observed output shape
- finite-value result
- coherence result and maximum error
- warnings or exception evidence when applicable
- reconciled output only when validation permits it

`VERIFIED` requires actual execution plus successful shape, finite, and coherence validation.

### Formal case record

Every formal matrix row records:

- game
- method
- expected state
- observed adapter state
- case pass/fail state
- actual-execution evidence
- duration
- warnings
- output shape and SHA-256 evidence
- finite and coherence evidence
- exception type, message, and traceback when present

The harness must retain all 40 case rows even if one or more cases fail.

### Runtime summary

The overall runtime result records:

- Run ID
- run directory
- status and formal-success flag
- expected, executed, passed, and failed case counts
- exact-version and module/distribution consistency evidence
- configuration and configuration SHA-256
- source/code hash evidence
- runtime environment evidence

## Coherence invariant

For a reconciled result `Y` and bottom-level rows `Y_bottom`, the following must hold within the
configured tolerance:

```text
S @ Y_bottom == Y
```

Failure of this invariant produces a validation failure and cannot be promoted to `VERIFIED`.

## Finite-value invariant

All accepted numeric inputs and every promoted reconciled output must contain only finite values.
NaN and positive or negative infinity are rejected.

## Shape invariant

The reconciled output shape must equal:

```text
(n_nodes, horizon)
```

A different shape is a validation failure even when upstream execution completed without raising.

## Determinism contract

- Formal seed defaults to `1`.
- Input arrays are generated deterministically per game.
- Every method within a game receives equivalent input evidence.
- Array evidence uses explicit little-endian float64 byte representation before SHA-256 hashing.
- ZIP members use deterministic order and fixed metadata.
- Repackaging unchanged evidence must produce identical ZIP bytes.

## Artifact schemas

### Primary runtime artifacts

```text
RUNTIME_CERTIFICATION.json
METHOD_RESULTS.json
INPUT_EVIDENCE.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

JSON documents must contain objects at the top level and must serialize without non-finite JSON
numbers. `SHA256SUMS` must cover exactly the primary JSON artifacts defined by the runtime schema.

### Package artifacts

```text
<run-id>.zip
<run-id>.zip.sha256
```

The ZIP must contain one Run ID prefix and exactly the primary runtime artifacts plus
`PACKAGE_MANIFEST.json`.

## Immutability contract

- A new formal attempt creates a new Run ID.
- Existing raw runtime artifacts are never silently modified by packaging.
- An identical existing ZIP may be reused.
- A differing existing ZIP or sidecar is preserved and rejected.
- A failed temporary ZIP is removed before publication.
- A mismatch must be investigated as incident evidence rather than deleted to manufacture success.

## Security and path contract

- Artifact filenames must be single safe path components.
- Absolute paths, `..`, duplicate members, and paths outside the Run ID prefix are rejected.
- Unexpected files are not included in the formal package.
- Secrets are not part of the runtime input or artifact schema.

## Excluded data contract

This component does not ingest historical lottery observations for model training, does not split
Train/Validation/Holdout/Prospective data, and does not calculate Hit@±1 or error metrics. Its
inputs are deterministic structural runtime-certification arrays, not forecasting evaluation data.
