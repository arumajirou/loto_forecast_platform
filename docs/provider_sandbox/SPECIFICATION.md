# Functional Specification

## Policy decision

A `SandboxPolicy` is valid only when all mandatory isolation controls are explicit. The schema fixes
network mode to `DISABLED`, root mode to `READ_ONLY`, `no_new_privileges=true`, and
`drop_all_capabilities=true`.

`untrusted_remote_code=true` with backend `NONE` is a schema error.

## Mount classes

| Kind | Requested mode | Notes |
|---|---|---|
| RUNTIME | READ_ONLY | reviewed provider runtime only |
| REPOSITORY | READ_ONLY | bounded source checkout |
| MODEL_SNAPSHOT | READ_ONLY | immutable model snapshot |
| INPUT | READ_ONLY | request and approved inputs |
| OUTPUT | READ_WRITE_TMP | isolated output only |
| TMPFS | READ_WRITE_TMP | source-less ephemeral storage |

Nested targets, `/home`, `/root`, container sockets, traversal and symlink components are rejected.

## Environment

The request may supply only keys in the policy allowlist. Keys matching token, secret, password,
private-key, authorization, cookie, DSN, database, MLflow, AWS, GCP, Azure, SSH or Docker patterns
are rejected before argv creation. Raw values are not persisted in process results.

## Argv construction

The builder receives a strict policy, strict request and injected backend evidence. It produces a
hashed tuple of arguments. Shell executables are forbidden, NUL bytes are rejected and metacharacter
arguments remain literal entries.

Bubblewrap uses explicit mounts and does not bind the host root. Bubblewrap GPU requests fail closed
because `CUDA_VISIBLE_DEVICES` is not kernel device isolation.

Rootless OCI requires a digest-pinned image and rootless backend evidence. It emits network, root,
user namespace, no-new-privileges, capability, PID, memory, CPU, file-limit, mount and device flags.

## Effective evidence

The verifier checks backend, network, root mode, privileges, capabilities, limits, mount identity,
environment key inventory and GPU device inventory. Source paths are compared through SHA-256 rather
than emitted as effective evidence.

Status precedence:

```text
MISMATCH   when any observed control disagrees
INCOMPLETE when no mismatch exists but required evidence is absent
VERIFIED   only when every required control is present and equal
```

## Child runner

The child runner receives an already validated plan, uses `shell=False`, starts a new process group,
redirects output to temporary files, monitors wall time and aggregate output size, and kills the
process group on timeout or output overflow. Only hashes, sizes, PID, exit code, duration and bounded
error code are returned.
