# Handoff

## Implemented

- strict immutable contracts;
- centralized transition matrix;
- optimistic revision decisions;
- event hash-chain generation and verification;
- semantic idempotency and duplicate evidence;
- injected clock;
- lease, heartbeat, expiry, takeover and fencing;
- event replay and immutable output preservation;
- focused deterministic, fault and property-test source;
- machine-readable configs and artifact inventory.

## Not implemented

- PostgreSQL, SQLAlchemy or Alembic;
- distributed transaction/outbox;
- Temporal, Dagster, Celery or Ray orchestration;
- API or worker integration;
- Prediction/Actual lock integration;
- Runtime Certification, Data Access Ledger or MLflow integration;
- production deployment.

## Next recommended PR

Implement a PostgreSQL repository adapter as an independent PR after this contract is reviewed. It
must prove transactional event+aggregate+idempotency commit, unique-key races, revision CAS, fencing,
process crash recovery and migration rollback without changing these contract semantics.
