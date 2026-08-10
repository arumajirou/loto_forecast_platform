# Unified all-model × all-game evaluation campaign

## Status

`MERGED_ON_MAIN / DEVELOPMENT_ONLY / HOLDOUT_CLOSED / PROSPECTIVE_CLOSED`

This document describes the executable campaign introduced for GitHub #247 / Linear TAJ-15 and merged through PR #248. It is a code contract, not evidence that every third-party model succeeds on every game.

Merged implementation evidence:

```text
PR=248
merge_sha=aae45ba9294499f51cc5f1564de1c6ccf5814230
exact_premerge_head=c7c8a039e7aa1aef34fbfd0af8dc2c41f67945a2
linux_ci_run=31371724178 SUCCESS
windows_portability_run=31371724143 SUCCESS
```

Later `main` commits may contain dependency or documentation updates. The implementation identity above is retained so the evidence remains reproducible. The merge itself does **not** prove that a real-data 174 × 6 run has succeeded.

## Purpose

The campaign answers two different questions without conflating them:

1. **Coverage:** Did every requested broad-catalog model × game combination receive a result row?
2. **Execution:** Which of those combinations actually executed successfully under the common protocol?

A complete matrix may therefore contain `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `UNAVAILABLE`, `FAILED`, `PARTIAL_SEEDS`, or `NON_STANDALONE_METHOD` rows. Those states are evidence, not rows to hide.

## Canonical games

The campaign uses `loto.game.geometry` as the single geometry source:

- `mini`
- `loto6`
- `loto7`
- `bingo5`
- `numbers3`
- `numbers4`

Select-number games retain strict ascending/distinct legality. Numbers3/Numbers4 retain digit order and repeated digits.

## Model inventory

The default plan is generated from `loto.models.catalog_full.build_catalog()`. At the audited inventory boundary this is the broad 174-entry inventory. The campaign does **not** reinterpret 174 registered entries as 174 runtime-certified models.

Every requested `catalog model × game` pair must appear exactly once in the catalog result matrix. Reconciliation methods are retained as `NON_STANDALONE_METHOD` because they transform base forecasts rather than independently produce them.

## Same-condition contract

Within one game, every executable candidate receives the same:

- development/holdout boundary;
- chronological rolling folds;
- fold test rows;
- approved seed inventory;
- canonical Hit@±1-first metric manifest;
- seven mandatory baselines;
- post-processing/legalisation identity;
- bounded search/resource budget identity;
- code/Git identity;
- prediction-before-actual sealing rule.

Across different games, the protocol is intentionally geometry-aware. Universe size, number of positions and legal outcome rules differ, so a single byte-identical protocol across games would be scientifically incorrect. `EvaluationProtocolV2` records the exact geometry and hashes the result-affecting conditions per game.

## Metrics

Primary:

```text
hit_at_1
```

Required accompanying metrics:

```text
position_hit_at_1
all_positions_hit_at_1
mae
mse
rmse
```

Per-position Hit@±1 values are retained in each seed result. Per-game leaderboards sort by Hit@±1 first, then all-position Hit@±1, then MAE.

## Mandatory baselines

Every game executes the canonical baseline registry under the same folds and seeds:

1. `random`
2. `fixed`
3. `mean`
4. `median`
5. `last`
6. `frequency`
7. `statistical_ar1`

Baseline predictions use only history preceding the target draw.

## Seed policy

The default approved seeds are:

```text
42
1729
20260730
```

For each required metric the campaign stores:

- count;
- mean;
- population variance;
- standard deviation;
- minimum;
- maximum;
- worst value;
- worst seed.

A model missing one or more approved seeds is not silently ranked as a complete all-seed result. Best-seed-only selection is not implemented.

## Prediction lock order

For each `game × candidate × seed`:

1. execute each development fold using only history available before the target row;
2. retain predictions and draw identity only;
3. write a new immutable prediction-lock JSON with `actuals_known=false`;
4. fsync the lock;
5. calculate and retain its SHA-256;
6. only then read the corresponding target actuals from the development frame;
7. calculate metrics.

The output directory itself is single-use. Reusing an existing campaign directory raises an error rather than overwriting evidence.

This is a development/OOF-style prediction seal. It does not open Holdout or Prospective.

## Routing

### Position/foundation routes

Compatible catalog entries are adapted to `ModelSpec` and executed with `PositionSeriesWorker`, passing `geometry.column_names()` explicitly. This removes the old implicit `n1..n7` assumption for routable workers.

### Candidate estimator route

Supported sklearn/LightGBM/XGBoost/CatBoost candidate estimators use a slot-conditioned binary candidate matrix. Each row identifies both the target slot and candidate value, so the same point-forecast contract can represent select-number and digit games without sorting digit games. Feature values are calculated from history only.

### Explicit non-routes

A broad catalog entry remains visible when it cannot safely enter the common point-forecast contract. Examples include standalone reconciliation methods, libraries whose isolated campaign has not been bridged to `PositionSeriesWorker`, or a model with a game-specific geometry restriction.

The correct response is a fail-visible status, not synthetic success.

## Commands

### Full default campaign

The primary merged command is:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

The input directory contains one file per canonical game:

```text
mini.csv
loto6.csv
loto7.csv
bingo5.csv
numbers3.csv
numbers4.csv
```

Each file must contain `draw_no` plus the target columns defined by the canonical game geometry. The campaign derives a common draw-step clock internally; calendar frequency is not allowed to become an accidental model advantage.

### Plan only

```bash
uv run loto3 campaign \
  --output unused \
  --plan-only
```

This enumerates the requested catalog × game matrix without executing models.

### Bounded synthetic smoke

```bash
uv run loto3 campaign \
  --synthetic \
  --synthetic-rows 40 \
  --games numbers3,loto7 \
  --models logistic \
  --seeds 1 \
  --folds 1 \
  --test-size 2 \
  --min-train-size 12 \
  --holdout-size 4 \
  --device cpu \
  --output /tmp/unified-campaign-smoke
```

The standalone compatibility entrypoint remains:

```bash
uv run python scripts/run_unified_campaign.py ...
```

Both command surfaces use the same packaged CLI implementation.

## Artifacts

A completed run contains at least:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/<game>.json
prediction_locks/<game>/<candidate>/seed-<seed>.json
SHA256SUMS
```

`model_game_results.csv` is the fail-visible matrix. A model is eligible for the cross-game macro summary only when it succeeds for every requested game.

## Non-claims

The campaign does not imply:

- every registered model is runtime-certified;
- every model supports every game;
- isolated providers are automatically shared-routable;
- every model receives equivalent internal architecture-specific HPO semantics;
- a failed/non-routable row may be discarded from coverage reporting;
- a complete real-data 174 × 6 experiment has been executed;
- Holdout is evaluated;
- Prospective is evaluated;
- a champion exists;
- a model is promoted.

The first execution goal is reproducible, complete and fail-visible comparison infrastructure. Forecast superiority remains a separate empirical result.
