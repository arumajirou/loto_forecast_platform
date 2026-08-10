# テスト計画書 / Test Plan

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

## 1. Purpose

Implementation correctness、game geometry、leakage resistance、runtime integrity、scientific evaluation、promotion governance、cross-platform packagingを分離して検証する。

`pytest PASS`をruntime certificationやforecast superiorityへ読み替えない。

## 2. Development order

```text
focused unit/contract test
-> focused smoke
-> Ruff / compile / type where relevant
-> affected integration tests
-> final full pytest
-> exact-head/current-main GitHub CI
```

重いfull CIを小変更ごとに反復しない。

## 3. Geometry tests

Canonical six-game tableについて:

- positions/domain/family;
- select distinct/ascending legality;
- digits position order/repeated values;
- outcome validation;
- geometry-derived dimensions;
- new unreviewed game-size/digit-count hard-code rejection.

#252 regression boundary:

- select `mean_hits` uses set overlap;
- Numbers3/4 `mean_hits` uses exact positional equality;
- repeated digits and digit order are preserved;
- shape width must equal `geometry.positions`;
- legacy Loto7 wrapper remains compatible.

## 4. Unified campaign tests

### 4.1 Plan completeness

Requested broad catalog × known games cardinality and uniqueness.

### 4.2 Six-game baseline matrix

Every canonical game receives all seven mandatory baselines.

### 4.3 Shared candidate route

At least one digit and one select game exercise a probability-bearing candidate estimator.

### 4.4 Point-only route

No fabricated PMF is introduced for point-only models.

### 4.5 Fail-visible coverage

Expected terminal states remain in the result matrix instead of disappearing.

### 4.6 Seed summary

All configured seeds are retained; mean, population variance, std, min/max and worst values/seeds are correct.

### 4.7 Prediction lock

Prediction evidence is durable and SHA-256 fixed before matching target actual scoring access.

### 4.8 Output immutability

Existing run output directories fail closed.

## 5. Decoder tests

### MAP compatibility

Historical MAP API remains valid.

### WITHIN_TAU optimality

Reduced select geometry result matches brute-force optimum.

### Digit utility

Constructed probability fixtures distinguish MAP and ±tau window-mass decisions while preserving positions.

### Unified routing

Digits route to digit WITHIN_TAU logic; select route to constrained DP.

### Invalid input

Reject negative/non-finite/invalid shape/zero-mass probability surfaces as specified.

Decoder theory tests are not OOF improvement tests.

## 6. Data/leakage tests

- required target columns;
- unique draw identity;
- monotonic chronology;
- finite targets;
- game legality;
- future information sentinel;
- raw immutability where applicable;
- development/Holdout separation;
- prediction-before-actual event order.

## 7. Metric tests

Verify:

```text
Hit@±1
position Hit@±1
all-position Hit@±1
MAE
MSE
RMSE
mean_hits family semantics
```

Select-only set/ranking semantics must not leak into digit-game positional metrics.

## 8. Theory guard tests

For every relevant game/tau fixture:

- exact IID-null reference is finite/in-range;
- `excess_vs_iid_null` target maps to the expected absolute target;
- legal absolute target at/below reference is accepted;
- absolute target above reference without declaration is rejected;
- explicit alternative hypothesis path is distinguishable;
- implied target outside [0,1] is rejected;
- unknown game is rejected.

Interpretation string/documentation must not call the IID-null optimum a universal ceiling for all possible data-generating processes.

## 9. Promotion v1/v2 tests

### Historical compatibility

v1 schema/evidence remains parsed as v1 and is not silently transformed to v2.

### V2 theory target

- v2 uses `implied_absolute_target`, not the raw excess value;
- aggregate Hit@±1 and worst-window Hit@±1 use the same effective target;
- current v2 tau is fixed to 1.

### V2 game binding

- missing sealed `game_id` -> fail;
- Holdout/Prospective game mismatch -> fail;
- policy/evidence game mismatch -> fail;
- matching sealed identity -> allowed to continue.

### Rules

Verify minimum windows/draws, drift stability, baseline comparison, degradation thresholds and first-failure reason code.

### Manual-only safety

Regardless of rule outcome:

```text
automatic_promotion=false
automatic_retraining=false
registry_write_allowed=false
```

All-pass result may be `ELIGIBLE_FOR_HUMAN_APPROVAL` but not `PROMOTED`.

### Artifact/schema roundtrip

V2 artifact generation, verification and CLI loading use v2 schema without being verified as v1.

## 10. Power/MDE tests

For `paired-score-normal-approximation-v1`:

- required-draw and MDE calculations are algebraically consistent up to integer ceiling;
- MDE decreases as draw count grows;
- higher multiplicity is conservative via smaller adjusted alpha and greater required sample;
- unsupported alternative is rejected;
- effect <=0 rejected;
- non-finite/non-positive score SD rejected;
- n_draws <=0 and bool rejected;
- power curve requires non-empty unique sorted positive integer counts;
- `target_power <= adjusted_alpha` rejected;
- valid Bonferroni-adjusted plan accepted when target power exceeds adjusted alpha.

Power tests establish calculation contract, not statistical truth for a future observed sample.

## 11. Runtime certification tests

For each runtime claim, unit tests are insufficient. Exercise applicable:

```text
dependency import
model load
input construction
inference
output shape
finite output
effective device
GPU PID/VRAM/utilization if CUDA claimed
CPU fallback detection
save/reload inference
cleanup / VRAM release
```

Exact model/revision/environment identity must accompany evidence.

## 12. NeuralForecast AutoModel tests

- official AutoModel class resolution;
- Optuna/Ray policy materialization;
- seed preservation;
- resource controls;
- `n_series` contracts for multivariate classes;
- model-specific precision guard;
- failed trial visibility;
- save/reload where requested.

Local inactive extensions must not be reported as active official AutoModels.

## 13. Isolated provider tests

AutoGluon/BasicTS/Time-Series-Library/Merlion/sktime and other isolated lanes must verify their own:

- locked environment;
- request/response schema;
- path containment;
- provider version/revision;
- focused load/forward/save/load operations;
- failure classification.

Do not infer isolated provider success from root `uv sync`.

## 14. Probabilistic platform tests

- 72-model catalog uniqueness/schema;
- native implementation coverage;
- backend availability probe;
- model/game/backend compatibility;
- config validation;
- plan/smoke/run state transitions;
- status/diagnose/compare;
- API authentication/run profile restrictions;
- stop/resume behavior where applicable.

## 15. Dependency/packaging CI

### Linux final gate

```text
locked install
Ruff format check
Ruff lint
compileall
full pytest
clean-tree verification
cleanup
```

### Native Windows

At minimum validate universal lock resolution, wheel build/import and tracked-file cleanliness according to the current Windows workflow.

Queued/cancelled jobs are not PASS.

## 16. Pull Request race gate

Before merge re-fetch:

- current main SHA;
- PR head/base SHA;
- draft/mergeable state;
- changed files;
- ahead/behind relation;
- latest exact-head/current-base CI;
- unresolved review threads;
- security/runtime-sensitive paths.

Use expected-head guarded merge. If head or main changes, prior exact-head proof may be stale.

## 17. Formal OOF tests

- chronological folds;
- immutable data/split identity;
- mandatory baselines;
- every configured seed;
- train-only fitted components;
- prediction-before-actual evidence;
- required metrics;
- protocol/data/code hashes;
- worst-seed retention;
- no best-seed-only selection.

## 18. Holdout tests

Holdout remains unavailable until explicit authorization.

When authorized verify:

- immutable Holdout identity;
- no prior actual access;
- pre-existing frozen protocol/model selection;
- no Holdout retuning;
- required baselines/metrics;
- sealed evidence and registry record.

## 19. Prospective tests

- prediction exists before future actual availability/read;
- immutable timestamp/hash;
- later actual ingestion separated;
- scoring reproducible;
- selected candidate identity stable according to policy;
- multiple window evidence as required.

## 20. Promotion acceptance tests

Promotion requires separately reviewed runtime, OOF, Holdout and Prospective evidence plus policy rules and human approval.

`champion=null`, `NO_MODEL_BEATS_BASELINE` and `NOT_ELIGIBLE` are valid safe outcomes.

## 21. Documentation tests

Current/live documents should:

- use the same capability-state vocabulary;
- distinguish broad inventory from executable routing;
- identify six canonical geometries consistently;
- document current theory/promotion/power contracts;
- not rewrite generated `MODEL_INVENTORY.md` or historical verification artifacts;
- not convert point-in-time runtime evidence into scientific claims.

## 22. Non-claims

CI success does not establish complete real-data 174 × 6 success, all-model OOF superiority, Holdout/Prospective success or production promotion.
