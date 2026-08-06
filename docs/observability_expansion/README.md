# Observability, Evaluation and OSS UI Expansion Blueprint v1

## Status

`DOCUMENTATION_ONLY / DESIGN_READY / IMPLEMENTATION_NOT_STARTED / REVIEW_REQUIRED`

This document set defines the additional implementation required to strengthen verification, evaluation,
logging, distributed tracing, metrics, data quality monitoring and operator interfaces without building a
new bespoke product UI.

The design is based on the current `main` at
`d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0` and preserves the ownership boundaries of:

- PR #127: API liveness, readiness and dependency observability;
- PR #124/#129: Data Access Ledger and research adapter;
- PR #123: provider-neutral Runtime Certification SDK;
- PR #121: strict configuration foundation;
- PR #79: old harness-specific observability assets, used only as reference because the branch is stale;
- PR #128: research model and method expansion blueprint.

## Goals

1. Make Hit@±1 the canonical primary metric across all research paths.
2. Include every result-affecting evaluation setting in protocol identity.
3. Standardize low-cardinality metrics, structured logs and OpenTelemetry spans.
4. Adopt OSS interfaces instead of developing a new integrated UI.
5. Connect Prometheus, Grafana Alloy, Loki, Tempo and Grafana through reviewed deployment assets.
6. Use MLflow UI for experiment comparison and model lifecycle inspection.
7. Activate Optuna Dashboard and Ray Dashboard for their native workloads.
8. Introduce Pandera at controlled DataFrame boundaries.
9. Add Evidently for data quality, drift and delayed-actual monitoring.
10. Add an optional `fev` adapter for external benchmark fingerprints and skill comparisons.
11. Preserve prediction sealing, Holdout and Prospective boundaries.
12. Treat live service connectivity and real runtime execution as separate certification gates.

## Documents

- `REQUIREMENTS.md`
- `FUNCTIONAL_SPECIFICATION.md`
- `BASIC_DESIGN.md`
- `DETAILED_DESIGN.md`
- `ARCHITECTURE.md`
- `OSS_SELECTION.md`
- `IMPLEMENTATION_PLAN.md`
- `EXECUTION_SCHEDULE.md`
- `TEST_PLAN.md`
- `MIGRATION_PLAN.md`
- `RISK_REGISTER.md`
- `TRACEABILITY_MATRIX.md`
- `PROMPTS.md`
- `HANDOFF.md`
- `CHANGELOG.md`
- `ARTIFACT_MANIFEST.json`
- `SHA256SUMS`

## Non-claims

This documentation PR does not:

- change source code, dependencies, lockfiles or workflows;
- start Prometheus, Grafana, Loki, Tempo, Alloy, MLflow, Evidently or Ray;
- certify PostgreSQL, MLflow, GPU, SMTP, Grafana, Loki or Tempo;
- execute model training, inference, OOF, Holdout or Prospective scoring;
- claim any accuracy improvement;
- authorize merge, deployment or production promotion.
