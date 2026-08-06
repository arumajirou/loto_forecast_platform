# Basic Design

## 1. Logical components

```text
GitHub Issue Form
  ↓
Experiment Plan PR
  ↓ review and merge
Approved Plan Store
  ↓ explicit dispatch
GitHub Control Workflow
  ↓ enqueue
Local Experiment Agent
  ↓ execute
MLflow / PostgreSQL / Object Storage
  ↓ evidence references
GitHub App
  ↓
Checks / Project / Result PR / Campaign Release
```

## 2. Repository layout

```text
experiments/
  plans/
  results/
  campaigns/

src/loto/experiment_control/
  contracts.py
  canonical.py
  validators.py
  approval.py
  dispatch.py
  evidence_index.py
  github_projection.py
  protocols.py

src/loto/experiment_agent/
  contracts.py
  queue.py
  workspace.py
  executor.py
  heartbeat.py
  cancellation.py
  github_app.py

.github/
  ISSUE_TEMPLATE/experiment-request.yml
  PULL_REQUEST_TEMPLATE/experiment-plan.md
  workflows/experiment-plan-validate.yml
  workflows/experiment-dispatch.yml
  workflows/experiment-result-verify.yml
  workflows/experiment-project-sync.yml

tests/
  experiment_control/
  experiment_agent/
```

The first PR adds only `experiment_control` Plan contracts and tests.

## 3. Authority separation

| Domain | Authority |
|---|---|
| proposal conversation | GitHub Issue |
| experiment plan | reviewed Git blob |
| approval evidence | signed/hashed approval object |
| execution state | durable lifecycle store |
| detailed metrics | MLflow/PostgreSQL |
| large artifacts | Object Storage |
| GitHub status | Check Run / Project projection |
| promotion | PR #137 subsystem |
| production binding | existing registry/deployment authority |

## 4. Branch and tag conventions

```text
Issue:        EXP-YYYYMMDD-NNNN
Plan branch:  exp/plan/EXP-YYYYMMDD-NNNN
Result branch: exp/result/EXP-YYYYMMDD-NNNN
Plan tag:     exp-plan/EXP-YYYYMMDD-NNNN
Result tag:   exp-result/EXP-YYYYMMDD-NNNN
Campaign tag: campaign/<game>/<period>-vN
```

Trial-level tags and releases are prohibited.

## 5. Initial compatibility rule

Until PR #121, #137, #138, and #140 are merged, adapters must use opaque evidence references.
They must not copy or silently fork those contracts.
