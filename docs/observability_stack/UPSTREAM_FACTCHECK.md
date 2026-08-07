# Upstream Fact Check

Checked on 2026-08-06 against official project documentation and release pages.

## Selected releases

| Component | Selected tag | Evidence classification |
|---|---:|---|
| Grafana | 13.1.1 | official Grafana download/release page |
| Grafana Alloy | v1.18.0 | official Grafana Alloy release page |
| Prometheus | v3.11.3 | official Prometheus release page |
| Loki | 3.7.2 | official Grafana Loki release page |
| Tempo | 2.10.5 | official Grafana Tempo release page; 3.0 was RC in reviewed material |
| BusyBox | 1.37.0-uclibc | utility-only backup image; digest resolution required |

Exact tags are committed as reviewed inputs. The runtime resolver records immutable manifest digests. No
digest is fabricated in the repository because this execution environment could not contact a container
registry.

## Configuration facts used

- Alloy can run from a mounted configuration file and exposes a local HTTP UI.
- `alloy validate` and `alloy fmt --test` are the intended native configuration checks.
- Alloy supports Prometheus scraping/remote write, OTLP receiving/exporting and Loki file ingestion.
- Grafana supports file-provisioned datasources and dashboards.
- Prometheus supports the remote-write receiver flag and TSDB retention flags.
- Loki TSDB schema v13 with filesystem storage is supported for local single-binary evaluation; Loki has no
  built-in authentication layer and must remain behind a network/security boundary.
- Tempo supports monolithic local storage evaluation and provides native configuration/health commands;
  Tempo has no built-in authentication layer.

## Deliberate deviations and limits

- Loki and Tempo filesystem backends are selected only for local single-node evaluation.
- No Docker socket discovery is used. The application metric target is explicit.
- All published ports bind to `127.0.0.1`.
- No Promtail deployment is introduced; Alloy is the routing layer.
- No public ingress, TLS proxy, OIDC or multi-tenant authentication is included.
- No dashboard query depends on run ID, request ID, trace ID, hashes, paths or free-form errors as metric
  labels.

## Native validation still required

When container tooling and registry access are available, execute exact resolved images:

```text
alloy fmt --test
alloy validate
promtool check config
loki -verify-config
tempo -config.verify
Grafana provisioning startup
Docker Compose config and live smoke
```

None of these native container checks is represented as PASS in the current environment.
