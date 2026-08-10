# Unified all-model × all-game evaluation campaign

```text
status: MERGED_ON_MAIN / DEVELOPMENT_ONLY
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
holdout: CLOSED_BY_DEFAULT
prospective: CLOSED_BY_DEFAULT
```

## 1. Purpose

`uv run loto3 campaign`は、requested broad-catalog model × gameについて:

1. **coverage** — 全組合せに結果行があるか;
2. **execution** — 実際にどのrouteが成功したか;
3. **scientific comparability** — 同じgame内で同一chronology/metrics/baselines/seeds/sealing contractを使ったか;

を分離して記録するdevelopment-only campaignです。

## 2. Implementation sequence

Relevant merged sequence:

```text
#248 unified model×game campaign
#249 explicit MAP / WITHIN_TAU constrained select decoder
#250 probability-bearing candidate routing to family-aware WITHIN_TAU
#252 geometry-general metrics and digit positional-hit correction
#253 theory-aware promotion semantics (downstream governance; not campaign auto-promotion)
#254 pre-experiment MDE/power planning (planning layer; not campaign scoring result)
```

## 3. Canonical games

```text
mini      select / 5 / 1..31
loto6     select / 6 / 1..43
loto7     select / 7 / 1..37
bingo5    select / 8 / 1..40
numbers3  digits / 3 / 0..9
numbers4  digits / 4 / 0..9
```

Select outputs are distinct/ascending. Digit outputs preserve position and repeated digits.

## 4. Model inventory

Default plan uses `loto.models.catalog_full.build_catalog()`.

Current broad inventory boundary: 174 entries.

Every requested model × game pair appears once. Reconciliation methods can appear as `NON_STANDALONE_METHOD`; unavailable or unsupported routes remain visible.

## 5. Status semantics

Examples:

```text
SUCCEEDED
PARTIAL_SEEDS
FAILED
UNAVAILABLE
NOT_ROUTABLE
UNSUPPORTED_GAME
NON_STANDALONE_METHOD
```

`matrix_complete=true` means coverage rows are complete. It does not mean all pairs succeeded.

## 6. Same-condition contract

Within each game, comparable candidates receive the same:

- development/Holdout boundary;
- chronological folds;
- target rows;
- game geometry;
- metric manifest;
- baseline manifest;
- configured seed inventory;
- result-affecting protocol identity;
- bounded resource/search configuration;
- prediction-before-actual rule.

Across different games the protocol is geometry-aware, so byte-identical geometry fields are neither required nor correct.

## 7. Metrics

Primary:

```text
Hit@±1
```

Required:

```text
per-position Hit@±1
all-position Hit@±1
MAE
MSE
RMSE
```

Geometry-general semantic rule:

- select `mean_hits`: set overlap;
- digits `mean_hits`: exact positional equality.

This prevents Numbers3/4 from losing digit order or repeated-digit meaning.

## 8. Mandatory baselines

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

Every baseline uses only history preceding the target.

## 9. Seed policy

Default seeds:

```text
42
1729
20260730
```

Each required metric retains count, mean, population variance, standard deviation, min, max, worst value and worst seed. Best-seed-only selection is prohibited.

## 10. Prediction lock order

For each `game × candidate × seed`:

```text
eligible-history fit/predict
-> persist prediction record with actuals_known=false
-> fsync
-> SHA-256
-> only then load/read matching target actual for scoring
-> metrics
```

Output directories are single-use.

This is development evidence; it does not open formal Holdout or Prospective.

## 11. Routing

### Candidate models

Shared candidate estimators may produce candidate probability/scores. Probability-bearing routes preserve:

```text
distribution_identity = row-normalized-slot-binary-probability-v1
```

### Digit decoder

Position-specific ±1 window probability/utility is maximized. Position order remains fixed.

### Select decoder

A legality-constrained dynamic program chooses a strictly increasing/distinct tuple maximizing WITHIN_TAU utility.

### Point-only models

No synthetic probability distribution is fabricated. Point forecast legalisation remains explicit.

### Non-routes

Broad entries without a safe compatible route produce a terminal status rather than fake success.

## 12. Commands

### Plan all

```bash
uv run loto3 campaign --output unused --plan-only
```

### Plan subset

```bash
uv run loto3 campaign \
  --output unused \
  --games numbers3,numbers4,loto7 \
  --models logistic,nf-nhits,chronos-2 \
  --plan-only
```

### Real development run

```bash
RUN_ID="unified-$(date +%Y%m%d-%H%M%S)"

uv run loto3 campaign \
  --input-dir /absolute/path/to/canonical-csv-directory \
  --output "artifacts/unified-campaign/${RUN_ID}" \
  --seeds 42,1729,20260730 \
  --folds 5 \
  --test-size 20 \
  --min-train-size 100 \
  --holdout-size 50 \
  --device auto \
  --precision 32
```

Expected input names for all games:

```text
mini.csv
loto6.csv
loto7.csv
bingo5.csv
numbers3.csv
numbers4.csv
```

### Bounded synthetic smoke

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

## 13. Resource/search controls

CLI exposes at least:

```text
--device auto|cpu|cuda
--precision 32|16-mixed|bf16-mixed
--max-trials
--parallel-trials
--max-steps
--wall-time-seconds
--gpu-count
--gpu-memory-bytes
```

These are part of result-affecting execution identity where applicable.

## 14. Artifacts

Minimum completed-run layout:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/<game>.json
prediction_locks/<game>/<candidate>/seed-<seed>.json
SHA256SUMS
```

Cross-game macro aggregation must not hide a model's failed requested game.

## 15. Theory-aware downstream interpretation

Campaign Hit@±1 results can later be interpreted through `TheoryAwareThreshold` using:

```text
absolute
excess_vs_iid_null
```

The campaign itself does not automatically declare a promotion target or alternative hypothesis.

## 16. Promotion downstream boundary

Promotion v2 can consume authorized Holdout + multiple Prospective score windows and binds them to sealed game identity. It may produce `ELIGIBLE_FOR_HUMAN_APPROVAL`, but campaign completion alone does not satisfy those later gates.

## 17. MDE/power planning boundary

Before a formal target window, `loto.evaluation.power_analysis` can estimate required paired draws or MDE using a pre-fixed paired-score SD and multiplicity-adjusted alpha.

This is planning evidence. It does not change campaign scores and is not a realized significance test.

## 18. Non-claims

This campaign implementation does not imply:

- every registered entry is shared-routable;
- every model succeeds on all six games;
- a complete real-data 174 × 6 run has finished;
- decoder improves every real OOF score;
- lottery draws are non-IID;
- Holdout/Prospective is complete;
- champion exists;
- promotion is authorized.
