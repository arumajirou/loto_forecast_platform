# Untrusted Provider Sandbox Contract v1

## Status

```text
PARTIALLY_VERIFIED
FOUNDATION_ONLY
FOCUSED_TESTS_PASS
REAL_KERNEL_ISOLATION_NOT_TESTED
REAL_BUBBLEWRAP_NOT_EXECUTED
REAL_ROOTLESS_OCI_NOT_EXECUTED
RUNTIME_CERTIFIED=false
SECURITY_CERTIFIED=false
```

This package defines a provider-neutral isolation contract for `trust_remote_code` and other
untrusted provider processes. It validates requested policy, builds argument arrays without a
shell, records injected backend identity, compares requested controls with effective evidence, and
writes tamper-evident evidence bundles.

It does not replace Runtime Certification SDK behavior. Model loading, tensor semantics, output
shape, finite values, save/reload, device evidence and replay remain owned by Runtime Certification.

## Supported backends

- `BUBBLEWRAP`: namespace and mount argv construction. GPU requests fail closed because environment
  filtering is not device isolation.
- `ROOTLESS_OCI`: digest-pinned image, network deny, read-only root, capability drop, no-new-
  privileges, resource flags and explicit OCI GPU device entries.
- `NONE`: forbidden whenever `untrusted_remote_code=true`.

## Safety defaults

- network disabled;
- root filesystem read-only;
- runtime, repository, model snapshot and input read-only;
- only output and tmpfs writable;
- no-new-privileges;
- all capabilities dropped;
- bounded PIDs, CPU, RAM, file size, output and wall time;
- explicit GPU allowlist;
- environment allowlist and secret-pattern deny;
- no Docker/Podman socket, SSH material, cloud credentials, database or MLflow credentials;
- canonical absolute paths and symlink-component rejection.

## Commands

```bash
PYTHONPATH=src python scripts/run_provider_sandbox.py validate-policy \
  --policy configs/provider_sandbox/default_policy.json

PYTHONPATH=src python scripts/run_provider_sandbox.py plan \
  --policy /absolute/policy.json \
  --request /absolute/request.json \
  --backend-evidence /absolute/backend.json

PYTHONPATH=src python scripts/run_provider_sandbox.py verify-effective \
  --policy /absolute/policy.json \
  --request /absolute/request.json \
  --effective /absolute/effective.json

PYTHONPATH=src python scripts/run_provider_sandbox.py verify-bundle \
  --bundle /absolute/evidence-directory
```

`execute-plan` is restricted to explicit `NONE` test fixtures and requires the
`--test-only-confirm-no-security-certification` acknowledgment. It is not a production sandbox
launcher.
