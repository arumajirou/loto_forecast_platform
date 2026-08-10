# Unified all-model × all-game evaluation campaign

## Status

`MERGED_ON_MAIN / PROBABILITY_DECODER_ROUTING_MERGED / DEVELOPMENT_ONLY / HOLDOUT_CLOSED / PROSPECTIVE_CLOSED`

This document describes the executable unified campaign introduced by PR #248 and its probability-aware decoder routing added by PR #250. It is a code contract, not evidence that every third-party model succeeds on every game or that the decoder improves real OOF accuracy.

Implementation evidence:

```text
PR_248_merge=aae45ba9294499f51cc5f1564de1c6ccf5814230
PR_248_exact_premerge_head=c7c8a039e7aa1aef34fbfd0af8dc2c41f67945a2
PR_248_linux_ci=31371724178 SUCCESS
PR_248_windows=31371724143 SUCCESS

PR_249_merge=83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f
PR_249_scope=explicit MAP/WITHIN_TAU constrained select decoder

PR_250_merge=8430d9f507ba735bf1df69930e057c974752bfdb
PR_250_exact_premerge_head=c3cefc9ce465aec9c98d4a0f0deca4a228d2058e
PR_250_linux_ci=31376812517 SUCCESS
PR_250_windows=31376812289 QUEUED_AT_AUDIT
```

Queued Windows evidence is not represented as PASS.

## Purpose

The campaign answers two separate questions:

1. **Coverage:** did every requested broad-catalog model × game combination receive a result row?
2. **Execution:** which combinations actually executed successfully under the common protocol?

A complete matrix can contain `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `UNAVAILABLE`, `FAILED`, `PARTIAL_SEEDS`, or `NON_STANDALONE_METHOD` rows. Those rows are evidence and must not be hidden.

## Canonical games

`loto.game.geometry` is the geometry source for:

- `mini`
- `loto6`
- `loto7`
- `bingo5`
- `numbers3`
- `numbers4`

Select-number games retain strict ascending/distinct legality. Numbers3/Numbers4 retain digit order and repeated digits.

## Model inventory

The default plan is generated from `loto.models.catalog_full.build_catalog()`. At the audited inventory boundary this is the broad 174-entry inventory. Registration is not runtime certification and does not imply 174 × 6 successful executions.

Every requested catalog-model × game pair must appear exactly once. Reconciliation methods remain `NON_STANDALONE_METHOD` because they transform base forecasts rather than independently create them.

## Same-condition contract

Within one game, every executable candidate receives the same development/holdout boundary, chronological rolling folds, test rows, approved seeds, metric/baseline manifest, result-affecting protocol identity, bounded resource/search identity and prediction-before-actual sealing rule.

Across games, `EvaluationProtocolV2` is geometry-aware. Position count, universe and legality differ by game, so forcing a byte-identical protocol across all games would be incorrect.

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

Per-game leaderboards prioritize Hit@±1 before all-position Hit@±1 and MAE.

## Mandatory baselines

1. `random`
2. `fixed`
3. `mean`
4. `median`
5. `last`
6. `frequency`
7. `statistical_ar1`

Baseline predictions use only history preceding the target draw.

## Seed policy

Default approved seeds:

```text
42
1729
20260730
```

For each required metric the campaign retains count, mean, population variance, standard deviation, minimum, maximum, worst value and worst seed. Best-seed-only selection is not implemented.

## Prediction lock order

For each `game × candidate × seed`:

1. execute development folds from eligible history only;
2. persist prediction/draw identity with `actuals_known=false`;
3. fsync the prediction lock;
4. compute its SHA-256;
5. only then read the corresponding target actuals for scoring;
6. calculate metrics.

Output directories are single-use. This is a development/OOF-style seal and does not open Holdout or Prospective.

## Routing

### Point-only position/foundation routes

Compatible catalog entries use `PositionSeriesWorker` with `geometry.column_names()` explicitly. If a route only returns point forecasts, PR #250 does not fabricate a probability distribution for it; the route remains explicit point legalisation.

### Probability-bearing candidate route

Supported sklearn/LightGBM/XGBoost/CatBoost candidate estimators use the game-agnostic slot-conditioned binary candidate bridge. PR #250 explicitly identifies this distribution as:

```text
row-normalized-slot-binary-probability-v1
```

It is not mislabeled as a native categorical PMF.

The resulting probability matrix is decoded with the explicit Hit@±1 objective:

- digit games: digit-family WITHIN_TAU/window-mass decoding;
- select games: legal constrained WITHIN_TAU dynamic-programming decoding.

Decoder objective, distribution identity and post-processing identity are retained in runtime evidence attached to the sealed seed evaluation so historical PR #248 evidence is not silently reinterpreted under the newer decoder protocol.

### Explicit non-routes

A broad catalog entry remains visible when it cannot safely enter the common point/probability forecast contract. Examples include reconciliation-only methods, isolated libraries without a shared adapter, game-incompatible models, unavailable dependencies or runtime failures.

The correct response is an explicit terminal status, not synthetic success.

## Commands

Full campaign:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Plan only:

```bash
uv run loto3 campaign --output unused --plan-only
```

Bounded smoke:

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

Compatibility entrypoint:

```bash
uv run python scripts/run_unified_campaign.py ...
```

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

A model enters the cross-game macro summary only when it succeeds for every requested game.

## Non-claims

The campaign/decoder routing does not imply:

- every registered model is runtime-certified;
- every model supports every game;
- every model successfully runs on all six games;
- every architecture receives identical internal HPO semantics;
- a complete real-data 174 × 6 experiment has been executed;
- the WITHIN_TAU decoder improves real OOF for every model;
- lottery draws are non-IID;
- Holdout or Prospective has been evaluated;
- a champion exists;
- promotion is authorized.

The infrastructure is designed for reproducible, complete and fail-visible empirical comparison. Forecast superiority remains a separate measured result.
