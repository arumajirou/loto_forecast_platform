# 仕様書 / Specification

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

## 1. Scope

本仕様はcurrent development evaluation、game geometry、model routing、decoder、metrics、prediction sealing、theory-aware target、promotion eligibility、pre-experiment power planningの外部観測可能な契約を定義する。

Formal Holdout / Prospective / production bindingはこの仕様の存在だけでは開放しない。

## 2. Canonical games

| game | family | positions | domain | legality |
|---|---|---:|---|---|
| `mini` | select | 5 | 1..31 | distinct + ascending |
| `loto6` | select | 6 | 1..43 | distinct + ascending |
| `loto7` | select | 7 | 1..37 | distinct + ascending |
| `bingo5` | select | 8 | 1..40 | distinct + ascending |
| `numbers3` | digits | 3 | 0..9 | ordered, repetition allowed |
| `numbers4` | digits | 4 | 0..9 | ordered, repetition allowed |

`loto.game.geometry`を単一のgeometry authorityとする。

## 3. Model inventory surfaces

### Broad

`loto.models.catalog_full.build_catalog()` / `uv run loto3 catalog`。

Current inventory boundary: 174 entries。

### Shared

`loto.models.catalog.MODEL_SPECS` / `uv run loto models list`。

Shared executionは`factory.py`、`workers.py`、`models/providers/**`へdispatchする。

### Isolated

`environments/**`、`*_campaign/**`、`adapters/**`、`scripts/run_*_provider.py`。

Broad registrationはshared/provider runtime successを意味しない。

### Probabilistic

`loto3 probabilistic`は別の72-model probabilistic catalogを使う。

## 4. Unified campaign CLI

### Plan

```bash
uv run loto3 campaign --output unused --plan-only
```

### Real development run

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

### Bounded smoke

```bash
uv run loto3 campaign \
  --synthetic --synthetic-rows 40 \
  --games numbers3,loto7 \
  --models logistic \
  --seeds 1 \
  --folds 1 --test-size 2 --min-train-size 12 --holdout-size 4 \
  --device cpu \
  --output /tmp/unified-campaign-smoke
```

## 5. Campaign configuration

Result-affecting fields include:

```text
games
model_ids
seeds
folds
test_size
min_train_size
holdout_size
gap
device
precision
max_trials
parallel_trials
max_steps
wall_time_seconds
gpu_count
gpu_memory_bytes
git_commit
```

Current unified primary tolerance is tau=1.

## 6. Matrix coverage

Every requested broad model × game pair receives exactly one result row.

Terminal states may include:

```text
SUCCEEDED
PARTIAL_SEEDS
FAILED
UNAVAILABLE
NOT_ROUTABLE
UNSUPPORTED_GAME
NON_STANDALONE_METHOD
```

Coverage completeness and execution success are separate fields/interpretations.

## 7. Split contract

Configured Holdout tail is excluded from development scoring.

Development uses chronological expanding/rolling folds satisfying:

```text
max(train_indices) < min(test_indices)
```

Holdout and Prospective are not scored by the unified development campaign.

## 8. Metric contract

Primary:

```text
Hit@±1
```

Required companion metrics:

```text
position Hit@±1
all-position Hit@±1
MAE
MSE
RMSE
```

`evaluate_outcomes()` semantics:

### select

```text
mean_hits = size(set(actual) ∩ set(predicted))
```

### digits

```text
mean_hits = count(actual[position] == predicted[position])
```

This prevents Numbers3/4 order/repetition loss.

All families compute position absolute/squared errors, RMSE, within-tau rate and all-position within-tau rate after geometry legality validation.

## 9. Baseline contract

Required baseline IDs:

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

Each prediction may use only history preceding its target.

## 10. Seed contract

Every configured seed is retained.

Minimum summaries:

```text
count
mean
population_variance
standard_deviation
minimum
maximum
worst_value
worst_seed
```

A candidate missing required seeds is not silently promoted as complete all-seed evidence.

## 11. Candidate routing

Shared candidate estimators receive target-free slot-conditioned candidate features.

Probability-capable candidate estimators may emit binary candidate probabilities/scores that are transformed into the explicit bridge identity:

```text
row-normalized-slot-binary-probability-v1
```

The bridge is not described as a native categorical PMF.

## 12. Position/foundation routing

Compatible shared `ModelSpec` values use `PositionSeriesWorker`.

`geometry.column_names()` must determine expected position columns. Output must be finite and match `geometry.positions`.

Provider-specific runtime can instead use isolated execution contracts.

## 13. Probability decoder

### Digits

For each position, select the value maximizing expected probability mass within ±tau, preserving digit order.

### Select

Given position × candidate probability/utility, find a legal strictly increasing distinct tuple maximizing the configured WITHIN_TAU utility using constrained dynamic programming.

### Point-only

Do not fabricate a probability matrix. Apply only point-route legality/post-processing.

Persist decoder objective, distribution identity and post-processing identity.

## 14. Prediction sealing

For every evaluated seed:

```text
predict
-> serialize prediction evidence with actuals_known=false
-> durable write/fsync
-> SHA-256
-> read corresponding target actual
-> score
```

Existing output directory reuse must fail.

## 15. Theory threshold schema

`TheoryAwareThreshold` fields:

```text
game
tau
semantics = absolute | excess_vs_iid_null
target
allow_above_null_ceiling
alternative_hypothesis
```

`assessment()` returns at least:

```text
game
tau
semantics
target
iid_null_ceiling
implied_absolute_target
status
alternative_hypothesis
interpretation
```

Validation:

- unknown game -> reject;
- implied absolute target outside [0,1] -> reject;
- absolute target above null ceiling without approved declaration -> reject;
- `allow_above_null_ceiling=true` without non-empty alternative hypothesis -> reject.

The reference is exact under the stated IID-null model only.

## 16. Promotion policy schemas

### v1

```text
autogluon-promotion-eligibility-v1
```

Historical fixed absolute Hit@±1 target semantics are preserved for existing evidence.

### v2

```text
autogluon-promotion-eligibility-v2
```

Adds:

```text
game
tau = 1
hit_at_1_target_semantics
allow_above_null_ceiling
alternative_hypothesis
```

For v2, evaluator:

1. validates Holdout/Prospective evidence;
2. requires `game_id` on every scored window;
3. requires all evidence games equal policy game;
4. computes `implied_absolute_target` from theory semantics;
5. applies it to aggregate and worst-window Hit@±1 rules;
6. evaluates Holdout→Prospective hit drop and MAE increase;
7. compares selected candidate against every mandatory baseline.

Possible automated decisions:

```text
ELIGIBLE_FOR_HUMAN_APPROVAL
NOT_ELIGIBLE
```

Never automatic promotion.

## 17. Promotion safety flags

Promotion decision artifact must retain:

```text
human_approval_required=true
human_approval_granted=false
automatic_promotion=false
automatic_retraining=false
registry_write_allowed=false
promotion_status=NOT_PROMOTED
```

A later explicit human approval operation is a separate state transition.

## 18. Power planning contract

Method identity:

```text
paired-score-normal-approximation-v1
```

`PowerPlan` fields:

```text
alpha in (0,1)
target_power in (0,1)
multiplicity >= 1
alternative = candidate_minus_reference_gt_zero
```

Derived:

```text
adjusted_alpha = alpha / multiplicity
```

Validation requires:

```text
target_power > adjusted_alpha
```

APIs:

```text
required_paired_draws(effect, score_sd, plan)
minimum_detectable_effect(n_draws, score_sd, plan)
power_curve(draw_counts, score_sd, plan)
```

Input rules:

- effect finite and >0;
- score_sd finite and >0;
- n_draws positive integer, bool rejected;
- power-curve counts non-empty, unique, sorted positive integers.

The result explicitly carries method, alpha, adjusted alpha, target power, multiplicity and score SD. This is planning evidence only.

## 19. Runtime evidence

A successful campaign result row is not by itself a provider certification artifact.

Formal runtime certification should capture applicable:

```text
model/repo/revision
artifact hashes
runtime/package lock
load
input
inference
shape/finite checks
requested/effective device
GPU PID/VRAM
CPU fallback
save/reload
cleanup
```

## 20. Artifacts

Unified campaign minimum outputs:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/<game>.json
prediction_locks/<game>/<candidate>/seed-<seed>.json
SHA256SUMS
```

Cross-game summary should include only candidates meeting its requested-game success contract; missing/failed game rows remain available in the detailed matrix.

## 21. Error semantics

Expected unsupported cases become explicit terminal rows when coverage should continue.

Protocol/data/output integrity errors fail closed.

Reject at minimum:

- unknown game;
- invalid geometry/domain;
- duplicate or non-monotonic identity;
- non-finite required values;
- prediction output shape mismatch;
- invalid probability surfaces;
- output directory reuse;
- theory/promotion game mismatch;
- invalid power planning inputs.

## 22. Non-claims

Implementation of this specification does not prove:

- complete real-data 174 × 6 execution success;
- all registered models are runtime-certified;
- decoder real-data improvement;
- non-IID lottery structure;
- Holdout/Prospective completion;
- champion selection;
- production promotion.
