# Platform Metrics v1 Verification Report

## Status

```text
PARTIALLY_VERIFIED
STACKED_ON_PR_147
FOCUSED_TESTS_PASS
COMPILEALL_PASS
AST_PASS
LINE_LENGTH_PASS
CARDINALITY_STRESS_PASS
GLOBAL_REGISTRY_ISOLATION_PASS
RUFF_BLOCKED_TOOL_UNAVAILABLE
MYPY_BLOCKED_TOOL_UNAVAILABLE
FULL_PYTEST_NOT_STARTED
APPLICATION_WIRING_DEFERRED
LIVE_PROMETHEUS_NOT_PROBED
GRAFANA_NOT_PROBED
```

## Repository and duplicate audit

```text
repository=arumajirou/loto_forecast_platform
default_branch=main
main_sha=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
stack_base_pr=147
stack_base_branch=feat/otel-instrumentation-v1
stack_base_sha=2c3e8226d71eb26e923533ad33a26fc0a6e165a7
head_branch=feat/platform-metrics-v1
```

Before branch creation, GitHub was checked for the same branch, same-purpose open/closed PRs and Issues,
main's `/metrics`, PR #127 health/readiness metrics, PR #131 design, PR #141 metric declarations and PR
#147 OpenTelemetry instrumentation. No same-purpose implementation existed.

## Ownership boundaries

- PR #127 owns request identity, health/readiness endpoints and five health metric families;
- PR #141 owns strict metric declarations and prohibited-label policy;
- PR #147 owns optional trace instrumentation;
- this PR owns the isolated concrete platform collector catalog;
- later integration owns the application scrape registry and callsite wiring;
- later operations PRs own Prometheus/Grafana deployment and certification.

## Changed scope

```text
src/loto/telemetry/prometheus/__init__.py
src/loto/telemetry/prometheus/catalog.py
src/loto/telemetry/prometheus/registry.py
tests/telemetry/test_platform_metrics_v1.py
docs/platform_metrics/METRICS_CONTRACT.md
docs/platform_metrics/CARDINALITY_BUDGET.md
docs/platform_metrics/TEST_PLAN.md
docs/platform_metrics/RUNBOOK.md
docs/platform_metrics/VERIFICATION_REPORT.md
docs/platform_metrics/ARTIFACT_MANIFEST.json
docs/platform_metrics/SHA256SUMS
```

No prerequisite-owned source file, `pyproject.toml`, `uv.lock`, workflow, FastAPI application, global
`/metrics` route, model provider, data pipeline, evaluation entrypoint, Runtime Certification, Data
Access Ledger, Holdout or Prospective path is changed.

## Dependency audit

`prometheus-client` is already a root dependency. No dependency or lockfile update is introduced.

Executed environment:

```text
Python=3.13.5
pytest=9.0.2
pydantic=2.13.4
prometheus-client=0.25.0
```

## Executed verification

```text
focused pytest=14 passed
metric families=29
catalog total upper bound=10,412 series
maximum family upper bound=4,680 series
maximum family=loto_model_inference_duration_seconds
full allowlist-combination stress=PASS
isolated CollectorRegistry construction=PASS
global registry unchanged=PASS
PR #127 metric-name disjointness=PASS
compileall=PASS
AST parse=PASS
new code/test line length >100=0
production secret-pattern scan=PASS
JSON manifest parse=PASS
SHA256SUMS verification=PASS
```

## Hardening history

The first focused run reported two failures:

1. batch validation called `.labels()` and created a zero-valued child series before the invalid batch was
   rejected;
2. the lazy-series test expected zero samples after construction, while the intentionally unlabeled
   telemetry-buffer gauge is exposed immediately at zero.

Validation was split from child-series resolution, so invalid batch validation is now side-effect free.
The lazy-series assertion now records the one intentional baseline gauge and verifies that only touched
label combinations create additional series. The complete suite was rerun successfully.

The cardinality formula was also hardened to include counter created timestamps and histogram `+Inf`,
count, sum and created-timestamp samples. The full allowlist stress test verifies actual series remain at
or below the conservative bound.

## Pending and blocked verification

```text
Ruff=BLOCKED_TOOL_UNAVAILABLE
mypy=BLOCKED_TOOL_UNAVAILABLE
PR_141_focused_regression=PENDING_COMPLETE_PRIVATE_CHECKOUT
PR_147_focused_regression=PENDING_COMPLETE_PRIVATE_CHECKOUT
PR_127_health_regression=PENDING_COMPLETE_PRIVATE_CHECKOUT
existing API regression=PENDING_COMPLETE_PRIVATE_CHECKOUT
full pytest=NOT_STARTED
application combined registry=DEFERRED
production callsite wiring=DEFERRED
live Prometheus scrape=NOT_PROBED
Grafana queries=NOT_PROBED
alert rules=NOT_IMPLEMENTED
load and memory budgets=NOT_MEASURED
GitHub Actions=PENDING_FINAL_HEAD
```

## Explicit non-claims

```text
PR #141 merged=false
PR #147 merged=false
PR #127 integrated=false
existing /metrics changed=false
global registry changed=false
production metrics emitted=false
Prometheus server configured=false
Grafana dashboard verified=false
alerts configured=false
Holdout accessed=false
Prospective accessed=false
production deployment=false
merge readiness=false
```

## Rollback

Before merge, close this stacked Draft PR. After merge, revert normally. No dependency, lockfile,
workflow, database, data, deployment or historical-artifact migration exists.

## Next PR

```text
ops/grafana-alloy-lgtm-v1
```

Do not treat the stack as merged. Re-audit prerequisites and preserve stacking or wait for integration.
