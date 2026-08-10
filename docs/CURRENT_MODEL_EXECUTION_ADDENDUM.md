# Current Model Execution Addendum

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

This addendum records execution/evaluation changes layered on top of the detailed `MODEL_EXECUTION_MATRIX.md` audit. It does not rewrite historical runtime artifacts.

## 1. Canonical broad campaign

`uv run loto3 campaign` remains the canonical six-game broad development comparison path:

```text
catalog_full planning
-> model × game matrix
-> compatible RuntimeModel / PositionSeriesWorker/provider route
-> explicit fail-visible status otherwise
-> family-aware decoding/legalisation
-> prediction lock before actual scoring read
-> geometry-aware metrics
-> seed aggregation
```

It is distinct from `loto experiment research` and `loto3 research`.

## 2. Six-game geometry

```text
mini      select / 5
loto6     select / 6
loto7     select / 7
bingo5    select / 8
numbers3  digits / 3
numbers4  digits / 4
```

The unified path now has geometry-general evaluation semantics through #252. In particular, digit hit counts are positional and do not use unordered set overlap.

## 3. Coverage versus execution

```text
174 registered
!= 174 shared-routable
!= 174 runtime-certified
!= 174 × 6 successful executions
!= 174 OOF-evaluated
```

The campaign records unsupported/non-routable/failure rows rather than dropping them.

## 4. Decoder/routing addendum

Probability-bearing candidate routes preserve:

```text
distribution_identity = row-normalized-slot-binary-probability-v1
```

and use:

```text
digits -> positional WITHIN_TAU/window-mass decoder
select -> legality-constrained WITHIN_TAU DP
```

Point-only models remain point-only.

## 5. Geometry-general metrics addendum (#252)

`evaluate_outcomes()` now:

- resolves game geometry explicitly;
- validates actual/prediction width and legality;
- uses positional hit count for digits;
- uses set overlap hit count for select games;
- reports position MAE/MSE/RMSE;
- reports within-tau and all-position-within-tau rates.

The legacy Loto7 `evaluate_draws()` remains a compatibility wrapper.

## 6. Theory-aware downstream governance (#253)

New promotion evidence can use `PromotionPolicyV2`:

- explicit game;
- tau=1 for current Hit@±1 promotion evidence;
- absolute or IID-null-relative target semantics;
- exact implied absolute target;
- sealed `game_id` match;
- aggregate/worst-window threshold rules;
- degradation and mandatory baseline rules.

This does not change model routing or make any model promoted.

## 7. Manual-only promotion

All-pass rules produce at most:

```text
ELIGIBLE_FOR_HUMAN_APPROVAL
```

The current contract keeps:

```text
automatic_promotion=false
automatic_retraining=false
registry_write_allowed=false
promotion_status=NOT_PROMOTED
```

## 8. Pre-experiment power planning (#254)

`evaluation.power_analysis` adds:

```text
PowerPlan
required_paired_draws
minimum_detectable_effect
power_curve
```

under `paired-score-normal-approximation-v1`.

This layer is intended to determine whether a planned paired evaluation can detect a declared effect size. It does not execute model inference and does not alter runtime capability labels.

## 9. Current library interpretation

Use `MODEL_EXECUTION_MATRIX.md` and `CAPABILITIES_AND_OPERATIONS.md` for full detail. Important boundaries remain:

- StatsForecast 41 broad vs 8 explicit shared IDs;
- MLForecast Auto 8 broad vs 2 direct shared MLForecast IDs;
- NeuralForecast 37 fixed broad + 36 Auto broad vs narrower direct fixed shared set;
- AutoGluon isolated environment/provider;
- BasicTS / Time-Series-Library / Merlion / sktime separate provider/campaign lanes;
- GluonTS shared route currently CPU-configured;
- TSFM runtime evidence must be read per exact model/revision;
- separate probabilistic surface contains 72 models.

## 10. Runtime evidence boundary

A campaign plan or successful adapter route does not upgrade a model to runtime-certified. Runtime claims still require actual load/inference/device/output evidence for the exact identity.

Current aggregate TSFM audit file records 21 total and 19 runtime-certified identities. It is not OOF evidence.

## 11. Scientific boundary

This addendum does not establish:

- complete real-data 174 × 6 success;
- all-model OOF superiority;
- Holdout completion;
- Prospective completion;
- champion selection;
- production promotion.
