# Platform Metrics v1 Test Plan

## Focused acceptance

1. the exact 29 required metric families are present;
2. PR #127 health/readiness metric names are not redeclared;
3. every label has a finite allowlist;
4. prohibited labels are absent;
5. total and per-family series upper bounds are deterministic and within budget;
6. two isolated registries can be constructed without collision;
7. construction does not mutate the global Prometheus registry;
8. counter, gauge and histogram values render with approved labels;
9. unknown metrics and missing/extra/unapproved labels are rejected;
10. metric-kind mismatches are rejected;
11. NaN, Infinity, negative values, out-of-range ratios and fractional count gauges are rejected;
12. batch validation has no collector-series side effect before mutation;
13. histogram buckets are present, unique and increasing;
14. horizon bucketing is bounded;
15. game-position geometry is enforced for position metrics;
16. metric series are lazy except for the intentionally unlabeled zero-valued buffer gauge;
17. all approved label combinations remain within the declared upper bound.

## Static checks

```text
Python AST parse
compileall
line length <= 100
JSON manifest parse
SHA256SUMS verification
production secret-pattern scan
remote Git blob parity
```

## Repository checks when a complete checkout is available

```bash
uv run ruff format --check src/loto/telemetry/prometheus tests/telemetry
uv run ruff check src/loto/telemetry/prometheus tests/telemetry
uv run mypy src/loto/telemetry/prometheus
uv run pytest -q tests/telemetry/test_telemetry_contract_v1.py \
  tests/telemetry/test_platform_metrics_v1.py
uv run python -m compileall -q src tests
uv run pytest -q
```

## Deferred integration checks

- current FastAPI `/metrics` endpoint with an explicit combined registry;
- PR #127 health/readiness regression in a complete checkout;
- live Prometheus scrape;
- Grafana dashboard queries;
- alert rules and runbooks;
- sustained update overhead and memory budget;
- production model, data, evaluation and registry callsite wiring.
