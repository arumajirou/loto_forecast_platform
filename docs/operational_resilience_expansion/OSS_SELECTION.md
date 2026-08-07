# OSS Selection

## Selected now

### Alembic

Use for explicit SQLAlchemy schema migration after re-auditing dependency compatibility. It supports
upgrade, downgrade, history, heads, current, and offline SQL. Autogeneration is review assistance,
not authority.

### Testcontainers

Use for ephemeral PostgreSQL and supporting integration services on the target host. Docker
availability is a prerequisite and absence is `BLOCKED`, not a skipped PASS.

### Toxiproxy

Use for deterministic network latency, timeout, reset, and service-unavailable scenarios.

### Bubblewrap or rootless OCI

Choose one primary backend after target-host capability detection. The common contract supports a
backend interface; do not claim both are verified without execution.

## Selected later

- pgBackRest for PostgreSQL backup/restore certification;
- Syft for SBOM;
- Cosign/SLSA for signing and build provenance;
- SOPS + age for secret files;
- Alertmanager and Blackbox Exporter for SLO-driven alerting;
- k6 and Schemathesis for API load and schema-driven tests.

## Deferred

- Temporal or Dagster until the internal lifecycle semantics are proven;
- Feast until external features require a real point-in-time feature store;
- OPA until policy is consumed by multiple services;
- Keycloak until multi-user OSS UI access justifies it.

## Rejection rule

Do not add an OSS dependency solely because it is listed here. The implementation PR must record:

```text
problem
existing internal capability
candidate OSS
version
license
maintenance status
Python/OS compatibility
security implications
dependency graph impact
rollback
target-host smoke
```
