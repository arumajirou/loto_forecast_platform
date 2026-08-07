# Runtime Certification SDK Foundation Architecture

## Status

```text
FOUNDATION_ONLY
PROVIDER_NEUTRAL
NO_EXISTING_PROVIDER_MIGRATED
REAL_GPU_EXECUTION_NOT_PERFORMED
ACCURACY_NOT_EVALUATED
```

## Purpose

Model-specific Draft PRs repeatedly implement the same runtime-evidence lifecycle. This foundation
extracts only the provider-neutral parts into `loto.runtime_certification`. Provider imports, model
construction, tensor preparation, native response parsing, license decisions, and model-specific
semantic checks remain outside the SDK.

## Re-audited implementations

| Model or framework | Representative PRs | Repeated common responsibilities |
|---|---|---|
| Chronos-2 | #82, #103 | strict request/output contracts, injected executor boundary, shape/finite/quantile checks, artifact seal |
| TimesFM 2.5 | #93 | identity pins, preflight, subprocess evidence, deterministic ZIP, independent archive review |
| Moirai 2.0 | #83, #87, #89, #98 | two-process replay, device/PID/UUID/VRAM, PID release, independent GPU rederivation, SHA256SUMS |
| TiRex-2 | #95, #100 | package/model identity, snapshot hash gate, output validation, replay, reviewed runtime lane |
| Toto 2.0 | #94, #99, #101, #102 | snapshot containment, package checks, input/output shape, quantiles, device/fallback, replay, ZIP |
| Sundial | #96 | sample/summary semantics, shape/finite checks, CPU/CUDA matrix, replay, semantic and ZIP verification |
| TabPFN-TS | #97, #105, #108 | checkpoint gate, CPU_SMOKE/GPU_FORMAL, two processes, PID/UUID/VRAM/release, evidence ZIP |
| NeuralForecast | #43, #90, #92 | load/save/reload, deterministic/stochastic replay, training and inference GPU evidence, runtime/accuracy separation |
| Merlion | #80 | isolated subprocess, timeout, package identity, save/load/re-predict, manifest and ZIP |
| StatsForecast | #51, #68, #70 | exact package inventory, CPU lifecycle, point output checks, save/load/re-predict, SHA and admission |

No pre-existing common SDK with this scope was found. Existing implementations stay unchanged and are
not silently redirected to this package.

## Layering

```text
provider adapter (future migration PR)
  - provider imports
  - native request construction
  - package/model-specific semantics
  - response parsing
  - license and runtime-lane policy
             |
             v
runtime_certification SDK
  contracts.py           strict shared evidence schema
  statuses.py            runtime/profile/origin/accuracy status axes
  identity.py            request/package/model/snapshot identity gates
  subprocess_runner.py   bounded process-tree executor + injected Executor protocol
  output_validation.py   shape, finite and quantile monotonicity
  device_evidence.py     CPU/GPU device and external evidence checks
  replay.py              save/reload/re-predict and equality/tolerance
  artifacts.py           manifest, SHA256SUMS and deterministic evidence ZIP
  verifier.py            two-process orchestration and fail-closed report construction
```

The common package imports no provider package or provider-owned project module.

## Trust and evidence axes

Three independent axes are mandatory:

1. `CertificationProfile`
   - `CPU_SMOKE`
   - `GPU_FORMAL`
2. `EvidenceOrigin`
   - `REAL`
   - `SYNTHETIC`
   - `INJECTED_FAKE`
3. `AccuracyStatus`
   - starts at `NOT_EVALUATED`
   - cannot be inferred from runtime success

A complete synthetic CUDA fixture may validate the verifier but remains
`runtime_status=PARTIALLY_VERIFIED`. Only `evidence_origin=REAL` can produce
`RUNTIME_CERTIFIED`.

## Fail-closed sequence

The high-level two-process API performs:

```text
request canonical SHA-256
→ installed package version and optional package artifact SHA-256
→ snapshot revision, containment, regular-file, size and SHA-256 checks
→ injected/real executor run A
→ adapter observation decoding
→ injected/real executor run B
→ adapter observation decoding
→ timeout and process-exit checks
→ CPU_SMOKE/GPU_FORMAL device contract
→ output shape, finite and quantile monotonicity
→ distinct-provider-process replay
→ save/reload/re-predict evidence
→ status boundary validation
```

Any mismatch raises a typed error. The SDK does not manufacture a PASS report from partial evidence.

The real executor starts a dedicated POSIX process session, reaps the direct child, and terminates
the process group on timeout or after the direct process exits. stdout and stderr are hashed while
streaming rather than accumulated in memory and are limited to 16 MiB per stream. The default host
environment is allowlisted; credential-bearing and process-injection overrides are rejected. Working
directories must be absolute existing directories with no symlink component, and process-start
failures do not retain the operating-system exception text.

On Linux, REAL evidence also binds the PID to a SHA-256 identity derived from kernel boot ID and
`/proc/<pid>/stat` start ticks. A missing process identity fails REAL certification closed; it is not
reconstructed from a later PID lookup.

## Provider-owned responsibilities

The SDK deliberately does not define:

- native model inputs or outputs;
- model class and parameter-count checks;
- quantile source semantics, sample semantics or point-strategy meaning;
- framework hooks such as Lightning callbacks;
- provider-specific save/load APIs;
- license approval;
- dependency-lock approval;
- historical-data or leakage policy;
- OOF, Holdout or Prospective evaluation;
- accuracy metrics or model promotion.

A provider adapter converts those facts into common contracts. That conversion is reviewed in a
separate provider-migration PR.

## Artifact boundary

The artifact helper provides:

- atomic JSON writing with randomized exclusive temporary files and directory fsync;
- explicit opt-in overwrite and output-symlink rejection;
- complete regular-file inventory with symlink rejection;
- portable POSIX-relative artifact names;
- streamed SHA-256;
- complete `SHA256SUMS` verification;
- deterministic ZIP timestamps, modes, ordering and compression;
- adjacent ZIP SHA-256 sidecar;
- ZIP traversal, duplicate/casefold collision, symlink, encryption, CRC, member-size, total-size and
  compression-ratio rejection.

SHA-256 proves byte consistency after sealing. It is not a digital signature, trusted timestamp or
producer-identity proof.

## Adoption model

This PR is add-only. Future migrations should select one provider, add a thin adapter, compare old and
new evidence in parallel, and remove provider-local common code only after parity is proven. Bulk
migration is explicitly prohibited.
