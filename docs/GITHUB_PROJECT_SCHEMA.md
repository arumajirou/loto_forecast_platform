# GitHub Project Schema — Runtime & Model Certification

This document defines the recommended schema for the GitHub Project:

- Project: `Loto Forecast — Runtime & Model Certification`
- URL: https://github.com/users/arumajirou/projects/1

The Project is an operational dashboard. It must not replace immutable run evidence, SHA-256 manifests, MLflow/registry records, or scientific gate artifacts.

## 1. Item granularity

Default item identity:

```text
one Project item = one canonical model identity × one canonical game
```

Do **not** create one Project card for every seed, fold, trial, artifact, or retry. Those belong in run artifacts/registry.

Repository-level blockers and campaign umbrella issues may also appear as Project items, but they must be visually distinguishable from model-game execution rows.

## 2. Required fields

| Field | Type | Values / meaning |
|---|---|---|
| Status | Single select | Planned / Ready / Running / Passed / Failed / Blocked / Done |
| Work Type | Single select | Model-Game / Campaign / Runtime / Infrastructure / Scientific / Governance |
| Model ID | Text | canonical collision-free ID |
| Library | Single select | builtin / sklearn / StatsForecast / NeuralForecast / NeuralForecast Auto / MLForecast / TSFM / probabilistic / other |
| Game | Single select | mini / loto6 / loto7 / bingo5 / numbers3 / numbers4 / n/a |
| Execution Surface | Single select | Shared / Provider / Isolated / Reconciliation / Not Routable |
| Capability State | Single select | REGISTERED / IMPLEMENTED / ROUTABLE / RUNTIME_CERTIFIED / LOTTERY_COMPATIBLE / OOF_EVALUATED / HOLDOUT_EVALUATED / PROSPECTIVE_EVALUATED / PROMOTION_ELIGIBLE |
| Runtime Status | Single select | NOT_RUN / PASS / FAIL / BLOCKED / UNAVAILABLE / NOT_ROUTABLE / UNSUPPORTED_GAME / NON_STANDALONE |
| Failure Class | Single select | NONE / MODEL / DATA / DEPENDENCY / OOM / TIMEOUT / HARNESS / SERIALIZATION / DEVICE / PORTABILITY / CI / GOVERNANCE / UNKNOWN |
| Device | Single select | CPU / CUDA / CPU_FALLBACK / n/a |
| Resource Class | Single select | CPU / GPU_LIGHT / GPU_MEDIUM / GPU_HEAVY / EXCLUSIVE_GPU / n/a |
| Runtime Certified | Single select | YES / NO |
| OOF Status | Single select | CLOSED / NOT_RUN / RUNNING / PASS / FAIL / NO_MODEL_BEATS_BASELINE |
| Holdout | Single select | CLOSED / AUTHORIZED / RUNNING / DONE |
| Prospective | Single select | CLOSED / SEALED / SCORED |
| Prediction Lock | Single select | NOT_APPLICABLE / MISSING / VERIFIED |
| Hit@±1 | Number | development/OOF only when scientifically comparable |
| All Position Hit@±1 | Number | companion KPI |
| MAE | Number | companion metric |
| RMSE | Number | companion metric |
| Baseline Delta Hit@±1 | Number | model minus selected required baseline reference |
| Worst Seed Hit@±1 | Number | no best-seed-only adoption |
| Seed Count | Number | number of retained evaluation seeds |
| Runtime Seconds | Number | observed task runtime |
| Peak VRAM MiB | Number | measured where reliable |
| Peak RSS MiB | Number | measured process memory |
| Run ID | Text | immutable run identifier |
| Git SHA | Text | exact code commit |
| Model Revision | Text | exact model revision where applicable |
| Evidence | Text | Actions/artifact/registry/release link |
| Last Run | Date | latest execution date |
| Priority | Single select | P0 / P1 / P2 / P3 |

If the Project field-count limit becomes tight, retain the governance/status fields in Project and move numeric detail to the evidence dashboard. Do not remove `Capability State`, `Runtime Status`, `Failure Class`, `Holdout`, or `Prospective` merely to save space.

## 3. View definitions

### 00 Executive

Layout: Table

Show:

- Status
- Work Type
- Model ID
- Game
- Capability State
- Runtime Status
- OOF Status
- Holdout
- Prospective
- Failure Class
- Last Run

Filter example:

```text
is:open
```

Purpose: repository owner can understand the current phase without opening logs.

### 01 Runtime Certification

Layout: Board

Group by: `Runtime Status`

Columns:

```text
NOT_RUN | PASS | FAIL | BLOCKED | UNAVAILABLE | NOT_ROUTABLE | UNSUPPORTED_GAME
```

Card fields: Model ID, Game, Device, Resource Class, Last Run.

### 02 Model × Game Matrix

Layout: Table

Group by: `Library`

Show: Model ID, Game, Runtime Status, Capability State, OOF Status, Hit@±1, Failure Class, Evidence.

Use saved filters for each canonical game.

### 03 Accuracy Leaderboard

Layout: Table

Filter:

```text
OOF Status:PASS
```

Sort priority:

1. Hit@±1 descending;
2. Worst Seed Hit@±1 descending;
3. MAE ascending;
4. RMSE ascending.

Never rank a row that lacks equivalent eligible folds, required baselines, complete seed inventory, or prediction-lock evidence together with a formally comparable row.

### 04 Failures & Blockers

Layout: Board

Group by: `Failure Class`

Filter:

```text
Runtime Status:FAIL,BLOCKED
```

Purpose: immediately separate model failures from infrastructure failures.

### 05 GPU / CPU

Layout: Table or Board

Group by: `Resource Class` or `Device`.

Show Peak VRAM MiB, Peak RSS MiB, Runtime Seconds, Runtime Status, Failure Class.

### 06 Roadmap

Layout: Roadmap

Recommended phase items:

1. Inventory / protocol freeze
2. Scheduler stabilization
3. Canonical identity smoke
4. Broad 174 × 6
5. Unified 250 × 6
6. Development-only OOF
7. Scientific review
8. Holdout authorization
9. Prospective
10. Human promotion review

### 07 Formal Gates

Layout: Table

Show only Holdout / Prospective / Promotion-related work.

Default expected state during current runtime work:

```text
Holdout=CLOSED
Prospective=CLOSED
```

## 4. Recommended charts

Create Project Insights charts for:

1. count by Runtime Status;
2. count by Game grouped by Runtime Status;
3. count by Library grouped by Capability State;
4. failures by Failure Class;
5. count by Device / Resource Class;
6. OOF Status by Library;
7. average Hit@±1 by Library and Game, only for comparable OOF rows;
8. average MAE by Library and Game;
9. average Peak VRAM MiB by Resource Class;
10. historical completed/open burn-up for the certification matrix.

Do not present a `matrix_complete=true` count as a success-rate chart without preserving explicit non-success statuses.

## 5. Automation boundary

Repository `GITHUB_TOKEN` is sufficient for repository Issues/PR/Actions reads used by the repository observability workflow, but user-level GitHub Projects v2 mutations generally require separate Projects-capable authentication.

Recommended secret name for future Project write automation:

```text
PROJECTS_TOKEN
```

The token should have the minimum permissions required to read/write the specific Project. A future sync workflow must fail closed when this secret is absent; it must not silently claim Project updates succeeded.

The current ChatGPT GitHub connector does not expose direct Project-v2 field/view mutation. Therefore this schema is version-controlled first, while repository-side Issues/labels/Actions/dashboard changes can be automated independently.

## 6. Normalized status rules

Never collapse all conditions into a single boolean `available` field.

```text
REGISTERED != RUNTIME_CERTIFIED
RUNTIME_CERTIFIED != OOF_EVALUATED
OOF_EVALUATED != HOLDOUT_EVALUATED
HOLDOUT_EVALUATED != PROSPECTIVE_EVALUATED
PROMOTION_ELIGIBLE != PROMOTED
```

A valid final scientific result may be `NO_MODEL_BEATS_BASELINE` with no champion.

## 7. Project update contract

When a formal run updates a Project item, update only fields evidenced by that run. The write payload should carry at minimum:

- model ID;
- game;
- Run ID;
- Git SHA;
- exact final runtime status;
- failure class;
- capability state reached;
- metrics only if scoring is authorized and comparable;
- evidence link;
- timestamp.

A failed Project write must not invalidate scientific run artifacts, and a successful Project write must not be treated as scientific evidence by itself.
