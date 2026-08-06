# Telemetry Contract v1 Test Plan

## Static checks

- Python compileall;
- Python AST parse;
- JSON manifest parse;
- line-length scan at 100 characters;
- secret-pattern review;
- SHA-256 verification.

## Focused contract tests

- strict unknown-field rejection;
- UTC timestamp normalization and naive-time rejection;
- bounded event-name and identity formats;
- finite duration and attribute values;
- attribute key, byte and nesting budgets;
- direct rejection of unredacted secret and protected-actual values;
- recursive secret, URI userinfo, bearer and query-parameter redaction;
- protected actual handling before and after an already-authorized reveal;
- nested context binding, inheritance and restoration;
- exception-type retention without exception-message retention;
- deterministic JSON and event SHA-256;
- prohibited metric labels, label count and value allowlists;
- duplicate metric registration and label-drift rejection;
- reviewed histogram buckets;
- optional-event drop and required-audit block behavior on buffer exhaustion;
- ordered bounded drain;
- deterministic property-style redaction and finite-number loops.

## Repository integration checks

These require a complete private checkout and are not performed by the isolated foundation fixture:

- existing API and JSONL event-reader regressions;
- all current observability/evaluation tests;
- full compileall;
- Ruff;
- mypy;
- full pytest.

## Future PR boundaries

The following belong to later PRs:

- PR #127 request-ID binding into telemetry context;
- OpenTelemetry SDK and OTLP exporter tests;
- Prometheus collector registration and scrape tests;
- pipeline/model/API instrumentation;
- Loki, Tempo, Alloy and Grafana integration.
