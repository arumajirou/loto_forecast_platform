# Data Contract

## Common rules

- schema version `1.0.0`;
- strict types, frozen models and unknown-field rejection;
- UTC-aware timestamps only;
- lowercase 64-character SHA-256;
- finite numeric values;
- canonical JSON with sorted keys and stable separators;
- duplicate JSON keys rejected by the evidence verifier.

## `SandboxPolicy`

Binds policy identity, backend, remote-code status, fixed network/root/privilege controls, mount plan,
environment allow/deny lists, executable allowlist, GPU device allowlist, resource limits, optional
digest-pinned OCI image and `policy_sha256`.

## `SandboxExecutionRequest`

Binds request/run identity, an absolute allowlisted executable, literal argument tuple, bounded
environment map, requested GPU devices and UTC issue time.

## `BackendEvidence`

Records injected backend availability, executable path/hash, bounded version, rootless observation and
UTC detection time. Availability cannot be asserted without executable identity.

## `SandboxArgvPlan`

Contains backend, immutable argv tuple, environment-key inventory and canonical plan SHA-256. It does
not contain a shell string.

## `EffectiveSandboxEvidence`

Contains independently observed controls. Any field may be absent, but absence causes `INCOMPLETE`.
Mount source identities use SHA-256 of the requested canonical path instead of exposing source paths.

## `SandboxProcessResult`

Contains outcome, PID, exit code, timeout flag, duration, stdout/stderr SHA-256 and sizes, bounded error
code and result SHA-256. Raw child output is not retained.

## `SandboxVerificationReport`

Contains status, verified flag, policy/effective bindings, missing checks, mismatches and report hash.
`verified=true` is possible only for `VERIFIED` with no gaps.
