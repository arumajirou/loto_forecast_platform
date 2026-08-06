# Migration Plan

## 1. Current state

The current platform exposes an inline FastAPI dashboard and `/metrics`, reads Run events and resource
samples from local JSONL, and has separate experiment tracking and KPI metric implementations.

## 2. Compatibility rules

- keep existing API routes during migration;
- keep `/health` compatibility as owned by PR #127;
- do not rename existing metrics without an alias and deprecation period;
- do not rewrite historical experiment artifacts;
- do not change Holdout or Prospective policies;
- do not move raw data;
- do not delete the FastAPI dashboard until OSS UI availability is certified.

## 3. Metric migration

1. inventory existing metrics;
2. assign canonical owner and semantics;
3. add new names alongside old names where required;
4. verify equal values;
5. update Grafana dashboards;
6. deprecate old names with a documented release window;
7. remove only after query and alert migration.

## 4. Log migration

1. define the event envelope;
2. wrap current JSONL emitters;
3. add trace correlation;
4. retain local JSONL as a fallback artifact;
5. deploy Alloy and Loki;
6. validate retention and redaction;
7. remove direct full-file API reads only after a replacement query path exists.

## 5. UI migration

Phase A:

```text
FastAPI dashboard + Grafana + MLflow
```

Phase B:

```text
FastAPI compatibility portal -> Grafana / MLflow / Optuna / Ray / Evidently links
```

Phase C:

```text
optional root redirect to Grafana, preserving OpenAPI and API routes
```

## 6. Rollback

Every phase must support:

- reverting code without data migration loss;
- disabling exporters through configuration;
- retaining local evidence;
- restoring prior dashboards;
- preserving old metric aliases during rollback;
- restoring MLflow database and artifact backups.

## 7. Historical data

Historical runs shall be tagged with their original metric and protocol schema versions. No backfill shall
claim information that was not recorded at execution time.
