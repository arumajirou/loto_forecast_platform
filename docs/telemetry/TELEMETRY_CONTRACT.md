# Telemetry Contract v1

## Status

`FOUNDATION_ONLY / EXPORTER_NEUTRAL / NO_RUNTIME_INSTRUMENTATION`

## Scope

This contract implements the Phase 2 boundary from
`docs/observability_expansion/IMPLEMENTATION_PLAN.md`:

- a strict structured event envelope;
- correlation context;
- secret and protected-actual redaction;
- deterministic event encoding and SHA-256;
- an exporter-neutral metric registry and cardinality policy;
- non-blocking bounded local buffering with explicit drop/block outcomes.

It does not add OpenTelemetry, Prometheus collectors, Grafana, Loki, Tempo, Alloy, MLflow,
FastAPI middleware, model instrumentation, or deployment assets.

## Event envelope

Required fields:

```text
schema_version
timestamp_utc
severity
event_name
component
status
```

Optional bounded identity:

```text
run_id
request_id
trace_id
span_id
game_id
model_id
model_revision
stage
fold_id
seed
duration_ms
error_code
reveal_state
attributes
```

The schema uses strict, frozen Pydantic v2 models with unknown-field and non-finite-number
rejection. Timestamps are normalized to UTC. Request and Run IDs are not interchangeable with
trace/span identity.

## Redaction

Redaction occurs before event validation. Sensitive keys include password, secret, token,
authorization, API key, DSN, database URL, SMTP, cookie, credential and private-key variants.
URI user information, bearer values and secret query parameters are also redacted.

Protected actual keys include actuals, targets, y_true, ground truth, winning numbers and
realized values. They become `[PROTECTED_ACTUAL]` unless the caller supplies
`reveal_state=AUTHORIZED`. The contract does not authorize reveal; it only records an already
authorized state from a later governed caller.

Exception messages are not stored. The safe factory retains only the exception type and a
bounded error code.

## Attribute budgets

```text
maximum top-level keys=32
maximum serialized UTF-8 bytes=4096
maximum nesting depth=6
```

Only JSON scalar, list and object values are accepted. NaN and Infinity are rejected.

## Correlation context

`bind_telemetry_context` uses `contextvars`, supports nested merging, and restores the prior
context after scope exit. It does not change PR #127 request-ID behavior; a later integration PR
may bind PR #127 IDs into this context.

## Metric cardinality policy

The registry is exporter-neutral. It creates no Prometheus collector. Every metric declaration
must provide a finite allowlist for each label. Maximum labels per metric is five.

Prohibited labels:

```text
run_id
request_id
trace_id
span_id
git_sha
model_revision
artifact_path
dataset_hash
config_hash
error_message
user_id
```

The foundation includes only three self-observation declarations:

```text
loto_telemetry_events_total
loto_telemetry_dropped_total
loto_telemetry_buffer_size
```

Platform metric implementation remains owned by `feat/platform-metrics-v1`.

## Failure behavior

The local buffer never waits for capacity.

- optional operational event on a full buffer: `DROPPED / BUFFER_FULL`;
- required audit event on a full buffer: `BLOCKED / BUFFER_FULL`;
- existing buffered evidence is not overwritten.

The caller remains responsible for stopping formal promotion after a required-audit `BLOCKED`
result. No exporter or pipeline is wired in this PR.

## Compatibility

Existing JSONL writers, API event readers, `/metrics`, `/health`, model providers, evaluation,
Data Access Ledger, Runtime Certification, Holdout and Prospective paths remain unchanged.
