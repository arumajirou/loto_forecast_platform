# Runtime Certification SDK Data Contract

## Schema

```text
runtime_certification_schema_version=1.0.0
```

All Pydantic models use:

```python
ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)
```

Unknown fields and implicit string-to-number conversion are rejected.

## Identity records

### RequestIdentity

- `request_id`
- canonical `request_sha256`
- `seed`
- `requested_device=cpu|cuda`
- provider-owned `input_schema_id`

The common verifier recomputes canonical JSON SHA-256 from the supplied request payload before process
execution.

### PackageIdentity

- distribution name
- exact installed version
- optional package wheel/sdist SHA-256
- optional source revision

Package metadata lookup is injectable for focused tests. Declaring an artifact SHA-256 requires the
exact artifact path.

### ModelIdentity

- logical model ID
- repository ID
- immutable revision
- optional config SHA-256
- optional weight SHA-256

### SnapshotIdentity

- snapshot root
- expected revision directory name
- one or more relative artifact identities

Every artifact records relative path, SHA-256, size and role. Absolute paths, traversal, backslashes,
Windows drive syntax, duplicate paths and case-insensitive collisions are rejected. Snapshot and file
symlinks are rejected before model loading.

## Process record

`ProcessExecution` records:

- unique run label;
- optional launcher-visible PID;
- timezone-aware start and finish times;
- exit code or timeout, never both;
- stdout/stderr SHA-256;
- optional response SHA-256.

Provider PID identity is retained separately in `DeviceEvidence`, because a generic
`subprocess.run()` boundary does not expose the child PID after completion.

## Output contract

`OutputContract` defines:

- exact expected nested shape;
- optional quantile axis;
- exact increasing quantile levels;
- monotonic tolerance.

`OutputEvidence` retains observed shape, finite state, quantile monotonicity and canonical output
SHA-256. Ragged, empty, non-numeric, boolean, non-finite, wrong-shape and crossing outputs fail.

## Device evidence

### CPU_SMOKE

Requires:

- requested and effective device both CPU;
- `cpu_fallback=false`;
- no GPU PID, UUID, VRAM or external GPU samples.

### GPU_FORMAL

Requires:

- requested and effective device both CUDA;
- `cpu_fallback=false`;
- provider GPU PID equals provider process PID;
- non-empty GPU UUID;
- positive peak VRAM;
- at least one matching external GPU sample;
- provider PID absent after exit.

`origin=REAL|SYNTHETIC|INJECTED_FAKE` is mandatory. Report origin and device origin must match.
Synthetic or injected evidence cannot produce `RUNTIME_CERTIFIED`.

## Replay evidence

Two distinct provider PIDs are required. Evidence records:

- save success;
- reload success;
- re-predict success;
- canonical hashes of both outputs;
- exact match;
- maximum absolute difference;
- allowed tolerance.

A non-exact replay is acceptable only when the measured maximum difference is within the declared
non-negative tolerance.

## Status contract

Runtime status:

- `EXECUTION_PENDING`
- `PARTIALLY_VERIFIED`
- `RUNTIME_CERTIFIED`
- `BLOCKED`
- `FAILED`

Accuracy status is independent:

- `NOT_EVALUATED`
- `EVALUATION_PENDING`
- `EVALUATED_NO_GAIN`
- `EVALUATED_GAIN`

A runtime-certified report defaults to `accuracy_status=NOT_EVALUATED`. The SDK has no API that
computes Hit@±1, MAE, MSE or RMSE and therefore cannot assert predictive success.

## Artifact contract

`ArtifactIdentity` is a canonical POSIX-relative path, SHA-256, size and role tuple.
`SHA256SUMS` must cover every regular file except itself. Extra, missing, duplicate, case-colliding,
symlinked or changed files fail verification.

The evidence ZIP is deterministic and accompanied by `<name>.zip.sha256`. ZIP verification is
read-only and checks byte hash, safe members, duplicate/casefold collisions, symlinks, encryption,
CRC and bounded resource limits.

## Non-claims

A valid common contract does not prove:

- a real provider was installed or executed unless origin is `REAL`;
- an external GPU was used when origin is synthetic or injected;
- model quality, accuracy improvement or baseline superiority;
- OOF, Holdout or Prospective completion;
- digital signature, trusted timestamp or non-repudiation.
