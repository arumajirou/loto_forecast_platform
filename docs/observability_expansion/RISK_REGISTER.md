# Risk Register

| ID | Risk | Impact | Mitigation | Stop condition |
|---|---|---|---|---|
| R-01 | duplicate work with PR #127 | conflicting readiness APIs | preserve ownership | health endpoints modified |
| R-02 | duplicate work with PR #123 | competing runtime evidence | consume SDK contracts | new runtime taxonomy created |
| R-03 | metric cardinality explosion | Prometheus instability | bounded label allowlist | unbounded label introduced |
| R-04 | secret leakage | security incident | pre-export redaction and tests | secret appears in log/trace |
| R-05 | protected actual leakage | invalid prospective result | reveal-state checks | actual emitted before reveal |
| R-06 | exporter blocks forecast | runtime outage | bounded async queue | unbounded call found |
| R-07 | telemetry loss hidden | false confidence | dropped-event counters | loss not observable |
| R-08 | protocol v2 rewrites history | invalid comparison | immutable legacy schema | historical record modified |
| R-09 | primary metric inconsistency | wrong champion | canonical registry | route uses different default |
| R-10 | stale PR #79 copied directly | obsolete configs/conflicts | reference only, rebuild on main | branch content merged wholesale |
| R-11 | Grafana exposed publicly | unauthorized access | loopback/auth/network policy | unauthenticated remote access |
| R-12 | MLflow live data lost | experiment loss | backup/restore drill | restore cannot reproduce run |
| R-13 | Loki/Tempo storage growth | disk exhaustion | retention and alerts | disk threshold exceeded |
| R-14 | GPU exporter unsupported | blind GPU monitoring | target-host probe/fallback | formal claim without probe |
| R-15 | Pandera duplicates temporal logic | conflicting validation | limit to table contract | availability logic duplicated |
| R-16 | Evidently mutates source data | provenance violation | immutable adapters | source write attempted |
| R-17 | external evaluation changes acceptance | governance drift | adapter-only role | fev replaces primary gate |
| R-18 | CI pre-run failure | unverifiable PR | resolve issue #58 | steps remain absent |
| R-19 | too many OSS services | operator burden | staged adoption | no owner/runbook |
| R-20 | custom UI regrowth | duplicate maintenance | portal-only policy | feature-rich bespoke UI proposed |
