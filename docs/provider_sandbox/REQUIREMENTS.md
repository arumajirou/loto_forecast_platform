# Requirements

## Functional requirements

- **PS-001**: represent `BUBBLEWRAP`, `ROOTLESS_OCI` and `NONE` explicitly.
- **PS-002**: reject `NONE` for untrusted remote code.
- **PS-003**: build argv arrays only; never build a shell command string.
- **PS-004**: default to disabled network and a read-only root filesystem.
- **PS-005**: permit write access only for output and tmpfs mounts.
- **PS-006**: validate mount source and target independently.
- **PS-007**: reject path traversal, non-canonical paths and symlink components.
- **PS-008**: enforce an environment allowlist and secret-pattern deny rules.
- **PS-009**: prohibit Docker/Podman sockets, SSH material, home-root mounts, cloud credentials,
  database credentials and MLflow credentials.
- **PS-010**: require positive PID, CPU, RAM, file, output and wall-time limits.
- **PS-011**: require an explicit GPU allowlist and reject unsupported device isolation.
- **PS-012**: accept backend detection evidence through injection.
- **PS-013**: compare requested policy to independently observed effective evidence.
- **PS-014**: classify missing effective evidence as incomplete, never verified.
- **PS-015**: classify mismatched effective evidence as mismatch, never verified.
- **PS-016**: bound child wall time and output size and retain only hashes and sizes.
- **PS-017**: write atomic evidence artifacts with a manifest and SHA-256 inventory.
- **PS-018**: reject evidence tampering, extra files, missing files, unsafe paths, duplicate keys and
  stale cross-object bindings.

## Non-functional requirements

- strict frozen Pydantic v2 contracts with `extra="forbid"`;
- finite numeric values and timezone-aware UTC timestamps;
- deterministic canonical JSON and lowercase SHA-256;
- no root dependency, lockfile, workflow, provider or production integration change;
- no Holdout or Prospective actual access;
- unavailable validation remains blocked or not executed, never passed.
