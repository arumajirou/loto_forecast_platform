# Execution Schedule

The schedule is gate-based rather than date-promised. Durations are engineering estimates and exclude
GitHub Actions infrastructure outages, external downloads, approval waiting time and Prospective calendar
windows.

| Wave | Work item | Estimated effort | Depends on | Completion gate |
|---:|---|---:|---|---|
| 0 | design review and duplicate audit | 1–2 engineer-days | none | ownership approved |
| 0 | GitHub Actions issue #58 resolution | administrative | owner/account | workflow steps execute |
| 1 | evaluation protocol completeness | 3–5 days | strict config review | focused/full tests |
| 1 | telemetry contract | 3–4 days | runtime/data contracts understood | schema tests |
| 2 | OTel instrumentation | 4–6 days | telemetry contract | OTLP trace smoke |
| 2 | Prometheus metrics expansion | 3–5 days | telemetry contract | scrape and cardinality tests |
| 3 | Alloy/Loki/Tempo/Grafana stack | 5–8 days | signals available | dashboards and restart smoke |
| 3 | host/GPU exporters | 2–4 days | target host | real exporter evidence |
| 4 | MLflow live certification | 5–8 days | PostgreSQL/artifact store | restart and restore proof |
| 4 | Pandera boundary schemas | 4–6 days | data contracts | pipeline regression |
| 5 | Evidently integration | 4–7 days | metric/data snapshots | delayed actual report |
| 5 | fev adapter pilot | 3–5 days | protocol v2 | mapping verification |
| 6 | FastAPI portal migration | 2–3 days | Grafana/MLflow ready | compatibility tests |
| 7 | OpenLineage/Pyroscope optional | 4–8 days | stable core | explicit operator need |

## Parallelism

Safe parallel tracks after Wave 0:

```text
Track A: evaluation protocol -> fev
Track B: telemetry contract -> OTel -> LGTM
Track C: MLflow live certification
Track D: Pandera -> Evidently
```

Shared files, dependencies and lockfile changes must not be edited concurrently. Dependency PRs are
serialized.

## Stop conditions

Stop the affected lane when:

- an overlapping open PR or branch is found;
- main moves and invalidates reviewed assumptions;
- CI cannot create workflow steps;
- telemetry exposes secrets or protected actuals;
- metric cardinality grows without a bound;
- OTel exporter blocks the forecast path;
- protocol v2 changes historical results without explicit migration;
- a live service cannot survive restart or restore;
- Holdout or Prospective access is requested without authorization.
