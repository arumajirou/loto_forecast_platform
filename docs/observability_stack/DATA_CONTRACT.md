# LGTM Operations Signal and Data Contract

## Prometheus

Only metric families and finite labels declared by PR #154 are accepted as platform metrics. Prohibited
labels include Run ID, request ID, trace/span ID, git SHA, model revision, artifact path, dataset/config
hash, free-form error and user ID.

## Loki

Input files are newline-delimited JSON. Alloy extracts only:

```text
component -> Loki label
severity  -> level Loki label
event_name -> parsed field, not label
```

The original JSON line remains the log payload. Protected actuals and secrets must already be redacted by
PR #141 before the file is written. Alloy is not a substitute for upstream redaction.

## Tempo

OTLP traces follow PR #147's bounded span contract. Raw HTTP paths, queries, SQL statements, parameters,
protected actuals and exception messages must not be exported. Correlation identifiers may be span
attributes but are not Prometheus labels.

## Grafana

Provisioned dashboards use stable datasource UIDs:

```text
prometheus
loki
tempo
```

Dashboard UID `loto-platform-overview-v1` is stable. UI edits are disabled; changes must be reviewed as code.
