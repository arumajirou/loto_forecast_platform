# Experiment Control, Approval, and Evidence Index Blueprint v1

## Status

```text
DOCUMENTATION_ONLY
GENERATED_AT=2026-08-06T17:32:00+09:00
REPOSITORY=arumajirou/loto_forecast_platform
OBSERVED_DEFAULT_BRANCH=main
OBSERVED_MAIN_HEAD=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
IMPLEMENTATION_NOT_STARTED
GITHUB_SETTINGS_NOT_CHANGED
ACTIONS_WORKFLOWS_NOT_CHANGED
HOLDOUT_NOT_OPENED
PROSPECTIVE_NOT_OPENED
MERGE_NOT_AUTHORIZED
```

## Purpose

This package defines a GitHub-centered experiment control plane for local LLMs, local forecasting
models, and proprietary API models.

GitHub is not the training or inference computer. Responsibilities are separated:

```text
GitHub
  = Control Plane
    proposal, plan review, approval, dispatch intent, status, checks, evidence index

Local CPU/GPU and proprietary APIs
  = Execution Plane
    training, HPO, inference, evaluation, retries, cancellation

PostgreSQL / MLflow / Parquet / Object Storage
  = Evidence Plane
    detailed runs, metrics, predictions, logs, traces, model artifacts
```

GitHub retains immutable identities, summaries, approval references, checks, and artifact locations.
It must not become the permanent store for model weights, raw datasets, large Parquet files, or full
runtime logs.

## Existing ownership boundaries

This blueprint consumes rather than duplicates current Draft work:

| PR | Existing owner | Boundary |
|---:|---|---|
| #121 | strict configuration | reuse after merge; do not create a competing global config |
| #123 | runtime certification | reference runtime evidence only |
| #124/#129 | Data Access Ledger | reference access evidence only |
| #125 | trusted time / Actual source | reference trusted evidence only |
| #127 | API readiness | do not recreate health endpoints |
| #131/#141 | evaluation, telemetry, OSS UI | consume metric/log/trace contracts |
| #132 | Feature Availability | reference feature evidence only |
| #133 | GitHub audit exporter | use for settings and repository evidence |
| #134 | Research Source Registry | reference source eligibility only |
| #137 | promotion subject/status | experiment approval cannot perform promotion |
| #138 | evaluation protocol completeness | consume canonical evaluation protocol |
| #139/#143 | generic GitHub feature foundation / Dependabot | reuse GitHub capability and settings design |
| #140 | durable lifecycle/outbox/fault design | Local Agent later consumes durable lifecycle |
| #122 | k-DPP-specific target control | model-specific precedent, not the common platform |

## Key decisions

1. An Issue Form is an intake UI, not the immutable experiment contract.
2. The reviewed `ExperimentPlan` file is the formal pre-execution contract.
3. A label alone never starts paid API use, GPU execution, Holdout, or Prospective work.
4. `workflow_dispatch` performs short validation/enqueue work only.
5. Long-running work is owned by an outbound-only Local Experiment Agent.
6. A GitHub App, not a long-lived PAT, writes Check Runs and status updates.
7. Actions artifacts are temporary transport, not permanent evidence storage.
8. Trials live in MLflow/DB; GitHub tracks runs and campaigns.
9. Promotion and deployment remain under PR #137 governance.
10. Every protected stage requires evidence-bound approval and fail-closed validation.

## Planned implementation sequence

```text
PR-1 Experiment Plan Contract v1
PR-2 Experiment Intake Forms and Templates v1
PR-3 Project Schema and Evidence Export v1
PR-4 GitHub App / Check Run Contract v1
PR-5 Local Experiment Agent Foundation v1
PR-6 Control Workflows v1
PR-7 Result PR and Evidence Index v1
PR-8 Proprietary API Budget Lane v1
PR-9 Campaign Tag / Release Governance v1
PR-10 Target-host Integration and Failure Tests v1
```

The recommended first implementation is `Experiment Plan Contract v1`. It is pure, dependency-light,
does not require Actions to work, and does not mutate GitHub settings.

## Package index

- Requirements and functional specification
- Basic, detailed, security, and data-contract design
- GitHub feature map and official fact-check report
- Projects, GitHub App, Local Agent, and Evidence Index designs
- Implementation roadmap, schedule, test/migration plans, runbook, and handoff
- Push-based implementation prompt
- Artifact manifest and SHA-256 inventory
