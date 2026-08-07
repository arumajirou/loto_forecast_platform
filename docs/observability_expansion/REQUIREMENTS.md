# Requirements Definition

## 1. Scope

The target is the cross-cutting verification, evaluation and observability plane of the forecasting
platform. Model algorithms and model-specific runtime adapters are outside this scope.

## 2. Functional requirements

### FR-EVAL-001 Canonical primary metric

The canonical primary metric shall be `hit_at_1`. The platform shall also store:

- `position_hit_at_1`;
- `all_positions_hit_at_1`;
- `mae`;
- `mse`;
- `rmse`;
- probabilistic metrics when the model emits a distribution.

Legacy names such as `mean_within_1` or `element_within_1` shall be mapped explicitly and never silently
treated as different metrics.

### FR-EVAL-002 Complete protocol identity

The protocol identity shall include every field capable of changing model selection or scientific
interpretation:

- data snapshot and split identity;
- feature set and availability identity;
- primary and secondary metrics;
- baseline inventory;
- alpha and multiplicity correction;
- bootstrap method and repetitions;
- conformal method and alpha;
- sentinel inventory and repetitions;
- post-processing and reconciliation;
- seed inventory and aggregation policy;
- search space and compute budget;
- software and code identity.

A human-readable protocol diff shall be generated for mismatches.

### FR-EVAL-003 Fair comparison

Comparisons shall use chronological Train, Validation, Holdout and Prospective boundaries. Scalers,
encoders, feature selection, causal screening, retrieval indexes and HPO shall be fit inside Train only.

All approved seeds shall be retained. Reports shall include mean, population variance and worst value.
Selecting only the best seed is prohibited.

### FR-LOG-001 Structured events

Application, worker and evaluation logs shall emit structured JSON with a bounded event name and stable
schema. Secret values, DSNs, tokens, unredacted exception strings and protected actuals shall not be
emitted.

### FR-TRACE-001 Distributed tracing

The platform shall emit OpenTelemetry traces for API requests and forecasting stages. Required span
stages include data validation, split creation, feature fitting, model load, fit, predict, lock,
actual read, scoring, persistence and promotion evaluation.

### FR-METRIC-001 Metrics contract

Prometheus metrics shall use low-cardinality labels. Run IDs, request IDs, trace IDs, hashes, raw paths
and free-form error messages shall not be labels.

### FR-UI-001 OSS UI policy

The platform shall not implement a new custom SPA or Streamlit dashboard for observability. It shall
delegate interfaces as follows:

- Grafana: operations, metrics, logs, traces and alerts;
- MLflow UI: experiments, metrics, artifacts and model lifecycle;
- Optuna Dashboard: Optuna studies;
- Ray Dashboard: Ray jobs, tasks, actors and resources;
- Evidently: data quality, drift and delayed performance;
- OpenAPI: API contract inspection.

The existing inline FastAPI dashboard may remain temporarily as a compatibility portal, then be reduced
to links or a redirect after OSS interfaces are certified.

### FR-DATA-001 DataFrame contracts

Pandera schemas shall initially cover four controlled boundaries:

1. Raw to normalized;
2. normalized to split;
3. prediction to scoring;
4. metrics to persistence.

### FR-OPS-001 Fail-closed readiness

PR #127 shall remain the owner of `/livez`, `/readyz`, `/health/dependencies`, request identity and
dependency readiness classification. Later probes shall reuse that interface.

### FR-OPS-002 Evidence and certification

A service being configured is not equivalent to being ready. Formal certification requires a live,
bounded, read-only probe and retained evidence.

## 3. Non-functional requirements

- Python 3.11 through 3.13 compatibility under repository policy.
- Pydantic v2 strict contracts for configuration and event payloads.
- Ruff, mypy, focused pytest and full pytest at final integration.
- No telemetry path may block forecasting indefinitely.
- Telemetry failure shall be classified explicitly; required audit evidence may fail closed, optional
  operational telemetry may degrade.
- OpenTelemetry and logging exporters shall use bounded queues and timeouts.
- Deployment assets shall be rootless where possible and shall not embed secrets.
- Raw data shall remain immutable.
- New dependencies require an isolated dependency PR and updated `uv.lock`.
- All operator-facing statuses shall distinguish `NOT_CONFIGURED`, `NOT_PROBED`, `DEGRADED`, `BLOCKED`
  and `VERIFIED`.

## 4. Acceptance requirements

The program is not considered complete until:

- the primary metric is consistent across the main research entry points;
- protocol mismatch reports identify field-level differences;
- local JSON logs correlate with traces through request and trace fields;
- Grafana can navigate from a metric to related logs and traces;
- MLflow displays a real, target-host experiment with hashes, seed metrics and artifacts;
- Optuna Dashboard opens a persisted real study;
- Evidently displays a real quality snapshot and delayed performance update;
- live probes exist for the services declared required by deployment;
- Holdout and Prospective remain unopened unless separately authorized.
