# LGTM Operations Stack v1 Test Plan

## Static checks

- required file inventory;
- exact service and image tag inventory;
- YAML and JSON parsing;
- Python AST and compileall;
- shell `bash -n`;
- line-length and secret scans;
- loopback-only ports;
- no Docker socket, privileged mode, host network or host PID;
- Grafana anonymous/sign-up disabled;
- datasource/dashboard stable UIDs;
- Loki TSDB v13 and retention;
- Tempo local backend and retention;
- Alloy signal routes and bounded queues;
- Prometheus scrape and alert-rule inventory;
- runtime lock validation fails closed.

## Native container checks

```text
alloy fmt --test
alloy validate
promtool check config and rules
loki -verify-config
tempo -config.verify
docker compose config
```

## Live checks

- all component readiness endpoints;
- all Prometheus internal targets `up`;
- real application metric arrival;
- JSON log write/read with correlation;
- OTLP trace write/read with parent-child relationship;
- Grafana datasource health and dashboard queries;
- alert transition with controlled fixture;
- restart persistence;
- backup and restore drill;
- retention and disk/resource evidence.

## Final repository checks

Run focused checks during implementation. Run Ruff, mypy, complete compileall and full pytest only after the
implementation and service-specific checks are complete.
