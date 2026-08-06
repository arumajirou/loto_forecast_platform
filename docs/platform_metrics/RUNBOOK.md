# Platform Metrics v1 Runbook

## Construct an isolated metric set

```python
from loto.telemetry.prometheus import PrometheusMetricSet

metrics = PrometheusMetricSet()
```

This does not change the global Prometheus registry.

## Record bounded values

```python
metrics.increment(
    "loto_pipeline_runs_total",
    labels={"stage": "PREDICT", "status": "PASS"},
)
metrics.set_gauge(
    "loto_evaluation_hit_at_1",
    0.75,
    labels={"game": "numbers4", "position": "N1", "split": "validation"},
)
metrics.observe(
    "loto_model_inference_duration_seconds",
    0.125,
    labels={"provider": "neuralforecast", "device": "cuda", "horizon": "1"},
)
```

Use `horizon_label()` to convert a positive integer horizon to the bounded label inventory.

## Render the isolated registry

```python
payload = metrics.render()
```

The returned bytes use the Prometheus text exposition format. This PR does not automatically expose the
payload through FastAPI.

## Integration rule

Do not register this complete catalog into `prometheus_client.REGISTRY` while PR #127's module-level
collectors are also imported without an explicit collision review. The application integration PR must:

1. create one approved application registry;
2. register platform metrics and health/readiness metrics exactly once;
3. update `/metrics` to render that registry;
4. run existing API tests and new scrape tests;
5. retain the legacy endpoint path and content type;
6. prove no duplicate timeseries registration;
7. retain bounded labels and cardinality budgets.

## Invalid update

Invalid values or labels raise before mutation. Classify optional metric emission failure as degraded
telemetry. Do not treat a successful metric update as immutable evidence, prediction locking or
promotion authorization.

## Cardinality diagnosis

```python
catalog = metrics.catalog
catalog.total_series_upper_bound()
catalog.series_upper_bound("loto_model_inference_duration_seconds")
metrics.touched_series_count()
```

The first two methods are conservative bounds. The final method counts currently exposed samples in the
isolated registry.
