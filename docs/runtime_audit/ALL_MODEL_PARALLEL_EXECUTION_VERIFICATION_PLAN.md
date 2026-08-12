# All-Model Parallel Execution & Functionality Verification Plan

## 1. Purpose

This document defines the evidence-first execution and verification plan for proving whether every canonical model identity in `loto_forecast_platform` can execute under a supported runtime contract and whether every routable/supported model-game path behaves functionally correctly under resource-aware parallel execution.

Tracking:

- GitHub umbrella: #269
- Scheduler/runtime evidence: #264
- Broad matrix: #265
- Unified matrix: #266
- Runtime implementation: PR #263
- Linear: TAJ-15

This plan is **runtime and functionality first**. Runtime success does not imply predictive accuracy, Holdout success, Prospective success, or promotion eligibility.

## 2. Current code-grounded inventory

The repository-owned planner derives identity counts from live registries:

```text
broad catalog identities          174
probabilistic catalog identities   76
unified canonical identities      250
canonical games                     6
broad model-game upper bound     1044
unified model-game upper bound   1500
```

The current inventory also reports provider scripts and NeuralForecast local extensions as execution surfaces. They must not be blindly added as new canonical identities without de-duplication.

The exact counts above are planning evidence from 2026-08-11 and **must be re-derived from the live registries at run time**. The plan never treats `174` or `250` as an immutable constant.

## 3. Definitions

### 3.1 Canonical identity

A canonical model identity is a collision-free model ID produced by the repository catalog/registry layer.

It is not the same thing as:

- provider script;
- model-game pair;
- seed;
- fold;
- trial;
- backend;
- revision;
- parameter set;
- runtime environment.

### 3.2 Planned execution unit

For the runtime matrix, one planned execution unit is one canonical model identity × one canonical game.

A planned unit may end in an explicit non-success state such as `UNSUPPORTED_GAME` or `NOT_ROUTABLE`. Those are valid matrix outcomes if evidenced; they are not silent skips.

### 3.3 Runtime success

Registration, importability, or a UI/API `available` flag is not runtime success.

Runtime success requires an actual invocation path that reaches the required runtime stage and produces auditable evidence.

### 3.4 Functionality certification

Functionality certification is stronger than a process exit code. It verifies the runtime contract described in Section 6.

## 4. Global acceptance KPI

The target is **not** "250 models succeeded".

The acceptance KPI is:

1. 100% canonical identity inventory coverage;
2. 100% planned matrix coverage with an explicit normalized final status;
3. 100% of runtime-successful routable pairs have required functionality evidence;
4. zero unresolved harness/infrastructure failures in accepted results;
5. real parallelism evidence, not only configured worker counts;
6. all accepted manifests/checksums verify;
7. runtime/functionality results remain separate from accuracy, Holdout, Prospective, and promotion decisions.

## 5. Execution phases

### Phase 0 — freeze inventory, protocol, and environment

Before launching models:

- run `scripts/plan_all_execution_identities.py`;
- derive Broad, probabilistic, and unified IDs;
- verify duplicate/collision invariants;
- verify probabilistic catalog/native registry identity parity;
- enumerate canonical games;
- inventory provider/local-extension execution surfaces separately;
- record exact Git SHA;
- record Python/uv/package/runtime versions;
- record CUDA/torch/device information;
- record CPU/RAM/GPU/VRAM snapshot;
- create a complete matrix plan before execution;
- freeze status taxonomy and artifact schema for the run.

Required initial evidence:

```text
IDENTITY_SUMMARY.json
UNIFIED_CATALOG.json
PROBABILISTIC_NATIVE.json
EXECUTION_SURFACES.json
RESOURCE_SNAPSHOT.json
RESOURCE_PLAN.json
MATRIX_PLAN.json
SHA256SUMS
```

### Phase 1 — weighted scheduler and harness certification (#264)

The full 1,044/1,500 sweeps are blocked until this phase passes.

Required gates:

- focused Ruff PASS;
- focused mypy PASS;
- focused pytest PASS;
- mixed CPU + GPU_LIGHT + GPU_MEDIUM + EXCLUSIVE_GPU smoke PASS;
- weighted slot accounting PASS;
- EXCLUSIVE_GPU no-overlap PASS;
- every lease has non-null release evidence;
- actual child PID/process tree persisted;
- per-task peak RSS persisted;
- per-task GPU PID/peak VRAM persisted where the platform exposes reliable attribution;
- CPU fallback evidence persisted and classified;
- Lightning shared-log race remains closed;
- Git provenance remains independent of isolated runtime cwd;
- evidence serialization does not reclassify successful model execution as model failure.

Current staged policy in PR #263:

```text
CPU             CPU/RAM governed
GPU_LIGHT       1 base GPU slot
GPU_MEDIUM      2 base GPU slots
GPU_HEAVY       3 base GPU slots
EXCLUSIVE_GPU   all resolved GPU slots
```

Only models with measured concurrency evidence may be placed in `GPU_LIGHT`. Unknown GPU-capable models must remain conservative.

### Phase 2 — all-identity one-path smoke

Purpose: detect routing/import/environment/model-level blockers before multiplying every identity across six games.

For every live canonical identity:

- choose one supported/routable smoke game when available;
- execute a minimal named runtime contract;
- record resource profile and actual resource use;
- produce one explicit normalized result;
- preserve logs/checksums;
- do not silently skip unavailable or unsupported identities.

Acceptance:

```text
canonical identities planned     = live unified count
canonical identities classified  = live unified count
silent skips                     = 0
unclassified results             = 0
```

A model may be classified as unavailable/non-routable/non-standalone when evidence supports it. This phase is not required to force an unsupported model into an artificial runtime path.

### Phase 3 — Broad 174 × 6 matrix (#265)

Run every Broad identity against all six canonical games under one normalized runtime protocol.

Planning upper bound from the current registry:

```text
174 × 6 = 1044 model-game units
```

Acceptance:

- exactly one terminal status per planned pair;
- all 1,044 planned pairs accounted for if the live count remains 174;
- no silent drop;
- no unresolved serialization/harness/logging/cwd/orphan-lease defect;
- all runtime successes carry functionality evidence;
- all non-success classifications carry diagnostic evidence;
- checksums pass.

### Phase 4 — probabilistic/unified expansion (#266)

Extend the completed Broad matrix to the collision-free unified catalog.

Current planner evidence:

```text
Broad          174 identities
Probabilistic   76 identities
Unified        250 identities
```

If these live counts still hold, the incremental probabilistic matrix is:

```text
76 × 6 = 456 units
```

and the total unified matrix is:

```text
250 × 6 = 1500 units
```

Acceptance additionally requires:

- probabilistic/native parity still passes;
- no model-ID collision;
- provider/local-extension surfaces are not double-counted;
- probabilistic execution statuses use the same evidence semantics as Broad statuses.

### Phase 5 — functionality certification

For every runtime-successful, routable/supported pair, verify the contract in Section 6.

### Phase 6 — development-only predictive evaluation

Only after runtime/functionality coverage stabilizes, reuse the repository's existing unified/research evaluation infrastructure.

Required scientific metrics:

- primary Hit@±1;
- position Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE.

Required baselines:

- Random;
- fixed value;
- mean;
- median;
- last value;
- frequency;
- statistical model baseline.

Required protocol:

- chronological folds only;
- Train-only preprocessing/tuning;
- all configured seeds retained;
- mean/variance/worst-seed evidence;
- prediction SHA-256 lock before actuals are read;
- paired statistical comparison and multiplicity correction;
- Holdout closed;
- Prospective closed;
- no automatic promotion.

## 6. Per-model functionality contract

Every runtime-successful pair is checked against all applicable items below.

### 6.1 Identity and environment

Record:

- model ID;
- library/provider;
- repository/model revision when applicable;
- runtime environment hash;
- code Git SHA/hash;
- config hash;
- data/synthetic contract hash;
- seed.

### 6.2 Import / construction / load

Verify:

- required dependency import;
- provider import;
- class/function construction;
- checkpoint/model loading when applicable;
- no hidden CPU fallback during declared GPU-only contracts.

### 6.3 Input contract

Verify:

- expected input columns/shapes;
- finite numeric inputs where required;
- chronological ordering;
- horizon/context compatibility;
- game geometry and position count;
- exogenous-variable shape/alignment when used.

### 6.4 Fit/update path

For trainable models:

- fit/update call actually executes;
- training stage status is explicit;
- device used by the training stage is recorded.

For zero-shot/non-trainable models:

- mark fit stage `NOT_APPLICABLE`, not `SUCCEEDED`.

### 6.5 Predict/inference path

Verify:

- inference call executes;
- output object is parseable;
- expected horizon returned;
- expected number of position/series outputs returned;
- no missing outputs.

### 6.6 Output validity

Verify:

- shape contract;
- all mandatory outputs finite;
- quantile/output-key contract when probabilistic;
- game/domain/geometry compatibility classification;
- decoded/calibrated domain status is not confused with raw model-domain runtime success.

### 6.7 Device and resource evidence

Record:

- expected device;
- observed device;
- scheduler PID;
- actual child PID;
- process tree;
- peak RSS;
- GPU PID mapping when available;
- peak VRAM;
- CPU/GPU utilization samples where useful;
- CPU fallback status.

A scheduler PID is not valid child-process evidence.

### 6.8 Capability-specific persistence

If a model/runtime declares save/reload capability:

1. save model/artifact;
2. reload from saved artifact;
3. run inference again;
4. verify shape/finite output;
5. record semantic/deterministic comparison policy.

If save/reload is unsupported, mark it explicitly rather than failing the entire runtime contract.

### 6.9 Evidence serialization

Successful fit/predict must remain distinguishable from post-run evidence serialization failure.

Never reinterpret `POST_RUN_SERIALIZATION_FAILED` as a model fit/predict failure without evidence.

## 7. Normalized status semantics

Prefer existing repository status taxonomy. Do not create a second incompatible enum without migration.

The matrix must distinguish at least these concepts when observed:

```text
SUCCEEDED
RUNTIME_SMOKE_SUCCEEDED
FAILED
UNAVAILABLE
NOT_ROUTABLE
UNSUPPORTED_GAME
NON_STANDALONE_METHOD
TIMEOUT
BLOCKED_GPU_RESOURCE
POST_RUN_SERIALIZATION_FAILED
```

Functionality evidence may add a separate certification dimension rather than overloading runtime status:

```text
NOT_TESTED
RUNTIME_EXECUTED
RUNTIME_CERTIFIED
FUNCTIONALLY_CERTIFIED
BLOCKED
FAILED
```

## 8. Parallel execution strategy

### 8.1 Global concurrency

The user-visible target is up to eight outer tasks, but the scheduler must derive the safe CPU/GPU split from live resources.

Previous evidence on the tested machine demonstrated:

- six-way concurrent execution for six specific NeuralForecast Auto GPU-light smokes;
- CPU2 + GPU6 global eight-task overlap.

This proves those specific profiles only.

### 8.2 GPU slot policy

The weighted scheduler uses base GPU slots. A typical tested 16 GiB profile used a 2 GiB base slot and a 2 GiB safety margin to permit six light slots, but capacity must be recalculated from current free VRAM.

Do not hard-code six concurrent GPU models for the full catalog.

### 8.3 Heavy/exclusive models

Foundation/zero-shot/TSFM/TimeLLM-like models remain exclusive until measured evidence supports a smaller profile.

A reduced TimeLLM smoke is a separate named contract and must never be silently substituted for a comparable default/broad accuracy run.

### 8.4 OOM/resource-pressure retry

When OOM/resource pressure occurs:

1. preserve logs/resource evidence;
2. classify the failed attempt;
3. make the resource profile more conservative;
4. rerun the **same model contract**;
5. do not silently reduce architecture/hyperparameters.

If a reduced model/runtime configuration is needed, create a new named contract and evidence tree.

## 9. Execution batching

To reduce blast radius and make failures attributable:

### Batch A — scheduler certification

Small mixed set:

- CPU model(s);
- proven GPU_LIGHT model(s);
- representative GPU_MEDIUM model;
- EXCLUSIVE_GPU model.

### Batch B — one-path identity smoke

All canonical identities, one routable smoke path each.

### Batch C — Broad 1,044 matrix

Batch by resource class/provider while preserving one global matrix plan.

Suggested execution order:

1. CPU-only/light statistical models;
2. GPU_LIGHT;
3. GPU_MEDIUM;
4. GPU_HEAVY;
5. EXCLUSIVE/foundation;
6. retry/remediation queue.

### Batch D — incremental probabilistic 456 matrix

Run after Broad normalization is stable.

### Batch E — functionality recheck queue

Re-run only pairs missing mandatory functionality evidence; do not repeat already immutable accepted evidence unnecessarily.

## 10. Stop conditions

Stop the affected lane when any of the following occurs:

- scheduler/resource accounting is inconsistent;
- child PID/process evidence is not attributable;
- repeated shared log/path collision;
- repository Git provenance is wrong;
- result serialization corrupts classification;
- output directory is reused without explicit resume semantics;
- matrix cardinality changes unexpectedly;
- duplicate model IDs appear;
- checksum verification fails;
- Holdout/Prospective data is accidentally accessed.

Do not continue a large sweep merely to maximize completion percentage if evidence integrity is compromised.

## 11. Required artifacts per accepted run

Minimum campaign-level artifacts:

```text
CONFIG.json
ENVIRONMENT.json
IDENTITY_SUMMARY.json
EXECUTION_SURFACES.json
RESOURCE_SNAPSHOT.json
RESOURCE_PLAN.json
MATRIX_PLAN.json
RESULTS.jsonl
FUNCTIONAL_CERTIFICATION.jsonl
RESOURCE_LEASES.json
CAMPAIGN_SUMMARY.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

Per attempt, retain:

- command/config;
- stdout/stderr/log;
- model/provider/revision;
- start/end timestamps;
- normalized status;
- exception/failure class;
- child PID/process tree;
- resource trace;
- output-shape/finite/device evidence;
- prediction/evidence artifacts when produced.

## 12. Run database / experiment tracking

Each run should emit a stable Run ID and persist, when available, to the repository's experiment/observability stores:

- Run ID;
- config;
- data hash;
- code hash;
- Git commit;
- model ID/revision;
- seed;
- prediction references;
- evaluation references;
- logs;
- GPU/device information;
- final status.

Filesystem artifacts remain immutable evidence even when the same data is mirrored into PostgreSQL, DuckDB, Parquet, or MLflow.

## 13. Reporting

Generate at minimum:

### 13.1 Identity summary

```text
canonical identities planned
canonical identities executed/classified
routable
unsupported
unavailable
non-standalone
runtime success
runtime failure
```

### 13.2 Matrix summary

```text
planned model-game units
completed units
silent drops
success
failure
unsupported
not-routable
unavailable
timeout
resource blocked
post-run evidence failure
```

### 13.3 Functionality summary

```text
load PASS/FAIL
input PASS/FAIL
fit N/A/PASS/FAIL
predict PASS/FAIL
shape PASS/FAIL
finite PASS/FAIL
device PASS/FAIL
child PID evidence PASS/FAIL
peak RSS evidence PASS/FAIL
peak VRAM evidence PASS/FAIL/N/A
CPU fallback PASS/FAIL/N/A
save/reload PASS/FAIL/N/A
```

### 13.4 Parallelism summary

Report actual overlap from lease/process timestamps:

```text
peak total active tasks
peak CPU tasks
peak GPU leases
peak GPU slots
exclusive overlap violations
resource wait time
wall time
sum individual durations
```

Configured worker limits alone are not execution evidence.

## 14. Project workflow

GitHub Project #1 (`Loto Forecast — Runtime & Model Certification`) is the visual dashboard.

Recommended hierarchy:

```text
#269 Master verification                              In Progress
  #264 Scheduler/resource certification              In Progress
  PR #263 Runtime remediation                         In Progress
  #265 Broad 1,044 matrix                             Todo / Blocked by #264
  #266 Unified 1,500 matrix                           Todo / Blocked by #265
```

Recommended Project fields:

- Status;
- Phase;
- Evidence Status;
- Execution Units;
- Runtime Status;
- Resource Profile;
- Git SHA;
- Run ID.

Use `scripts/sync_all_model_verification_project.sh` to add the tracked items and set the basic statuses/units from the command line because the connected repository API does not expose GitHub Projects v2 mutation directly.

## 15. Promotion boundaries

The following remain closed during runtime/functionality verification:

```text
Holdout evaluated     = false
Prospective evaluated = false
Promotion             = false
```

A runtime-certified model is only eligible to enter the development-only accuracy comparison. It is not a champion and must not be promoted automatically.
