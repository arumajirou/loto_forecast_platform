# LGTM Operations Stack v1 Handoff

## Review order

1. PR #141 telemetry contract
2. PR #147 OpenTelemetry instrumentation
3. PR #154 platform metrics
4. this stacked operations PR

After prerequisite merges, retarget to current main and repeat all static, native and live checks.

## Immediate operator prerequisites

- Docker Engine with Compose v2 and Buildx;
- registry/network access to resolve image manifests;
- sufficient disk for the configured retention;
- mode-0600 Grafana credential files;
- explicit application metrics target and JSONL directory;
- no conflicting local ports.

## Remaining gates

- immutable digest resolution and archived lock evidence;
- native config validators using exact images;
- live component startup/readiness;
- application metrics/logs/traces write/read;
- Grafana datasource/dashboard evidence;
- restart persistence and backup/restore drill;
- vulnerability and license scan;
- resource/capacity measurements;
- independent review and explicit human approval.

## Next planned PR

```text
ops/host-exporters-v1
```

Do not add node_exporter or dcgm-exporter to this PR. Their host privileges, labels and consumer-GPU support
require a separate fact-check and risk review.
