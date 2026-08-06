# Traceability Matrix

| Requirement | Design | Implementation lane | Verification |
|---|---|---|---|
| FR-EVAL-001 | metric registry | evaluation protocol PR | primary metric tests |
| FR-EVAL-002 | protocol v2/diff | evaluation protocol PR | hash and diff tests |
| FR-EVAL-003 | seed/baseline policy | evaluation protocol PR | aggregation and baseline tests |
| FR-LOG-001 | event envelope/redaction | telemetry contract PR | contract and leak tests |
| FR-TRACE-001 | span hierarchy | OTel PR | in-memory/OTLP tests |
| FR-METRIC-001 | metric registry/cardinality | telemetry and metrics PRs | series-count tests |
| FR-UI-001 | OSS interface plane | operations/UI migration PRs | datasource/UI smoke |
| FR-DATA-001 | four Pandera boundaries | Pandera PR | schema regression |
| FR-OPS-001 | PR #127 ownership | integration design | no duplicate endpoint test |
| FR-OPS-002 | live certification gates | service PRs | restart/restore evidence |
