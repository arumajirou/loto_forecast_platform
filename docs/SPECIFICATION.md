# 仕様書 / Specification

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T18:59+09:00
repository: arumajirou/loto_forecast_platform
audited_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
```

## 1. Scope

本仕様は現在の共通development evaluation、game geometry、model routing、decoder、prediction sealing、artifact出力の外部観測可能な契約を定義する。

Formal Holdout、Prospective、production promotionの実行仕様はこのdocumentだけでは開放しない。

## 2. Canonical games

`known_games()` が返すcanonical gamesを対象とする。

| game | family | positions | domain |
|---|---|---:|---|
| `mini` | select | 5 | 1..31 |
| `loto6` | select | 6 | 1..43 |
| `loto7` | select | 7 | 1..37 |
| `bingo5` | select | 8 | 1..40 |
| `numbers3` | digits | 3 | 0..9 |
| `numbers4` | digits | 4 | 0..9 |

Select outcomeはstrict ascending/distinct、digits outcomeはordered/repetition allowed。

## 3. CLI

### 3.1 Plan only

```bash
uv run loto3 campaign --output unused --plan-only
```

要求されたbroad catalog × game pairを列挙し、model inferenceを実行しない。

### 3.2 Development run

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

### 3.3 Synthetic smoke

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

Compatibility script:

```bash
uv run python scripts/run_unified_campaign.py ...
```

## 4. Configuration contract

主要result-affecting fields:

- games
- model IDs
- seeds
- folds
- test size
- minimum train size
- holdout size
- gap
- device
- precision
- max trials
- parallel trials
- max steps
- wall-time/resource budget
- Git/code identity

Primary tolerance `tau` はunified campaignでは1に固定する。

## 5. Matrix coverage contract

Default model inventoryは`catalog_full.build_catalog()`。

各requested model × game pairは**exactly one** catalog result rowを持つ。

許容terminal state例:

```text
SUCCEEDED
PARTIAL_SEEDS
FAILED
UNAVAILABLE
NOT_ROUTABLE
UNSUPPORTED_GAME
NON_STANDALONE_METHOD
```

Failure/non-routeを行ごと削除してcoverageを良く見せてはならない。

Mandatory baseline rowsはcatalog rowsとは別sourceとして保持する。

## 6. Split contract

Input frameの最後のconfigured Holdout sliceはdevelopment executionから分離する。

Development portionにchronological expanding rolling foldsを作る。

各foldで:

```text
train indices < test indices
```

を満たす。

Holdoutはunified campaignでscoringしない。Prospectiveもscoringしない。

## 7. Metric contract

Primary metric:

```text
hit_at_1
```

Required point metrics:

```text
hit_at_1
position_hit_at_1
all_positions_hit_at_1
mae
mse
rmse
```

Per-position詳細をseed resultへ保持する。

Per-game leaderboardの優先順位はHit@±1-firstとする。

## 8. Baseline contract

必須baseline IDs:

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

全baselineは対象testより前のhistoryだけを使う。

## 9. Seed contract

Configured seedはすべて実行・保存対象。

Metric summaryは最低限:

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

を含む。

Missing seedがあるcandidateをfull all-seed successとして黙ってrankしない。

## 10. Candidate feature/routing contract

Candidate estimator routeはslot-conditioned candidate rowsを構築する。

代表field:

- draw identity
- candidate value
- slot index
- candidate scaling
- slot scaling
- all-history frequency
- recent-window frequency
- gap since occurrence
- training label

Featureはtarget rowより前のhistoryのみから生成する。

Supported candidate estimator familyはshared `RuntimeModel` contractへ適合させる。

## 11. Position/foundation routing contract

Compatible `ModelSpec`は`PositionSeriesWorker`へ渡す。

`position_columns=geometry.column_names()`を明示し、Loto7固定列を暗黙前提にしない。

Outputは対象geometryのpositions数と一致しfiniteでなければならない。

## 12. Probability decoder contract

Probability-bearing candidate routeはPR #250以降、family-specific WITHIN_TAU decodingを行う。

Distribution identity:

```text
row-normalized-slot-binary-probability-v1
```

### Digits

各position candidate probabilityに対し、±1 windowの期待massを最大化するpointを選ぶ。Digit orderを保持する。

### Select

Position × candidate marginalから、strictly increasing legal tupleのexpected WITHIN_TAU utilityを最大化するconstrained decoderを使う。

### Point-only worker

Probability matrixをfabricateしない。Point routeとしてlegalisationする。

Decoder objective / distribution identity / post-processing identityをruntime evidenceへ保持する。

## 13. Prediction sealing contract

各seed評価は次の順序を守る。

```text
predict
-> serialize prediction evidence (actuals_known=false)
-> durable write/fsync
-> SHA-256
-> only then read matching target actuals
-> score
```

既存output directory再利用はfailする。

## 14. Artifact contract

Completed runは最低限次を含む。

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/<game>.json
prediction_locks/<game>/<candidate>/seed-<seed>.json
SHA256SUMS
```

Cross-game macro summaryはrequested全gameで成功したcandidateだけを対象にする。

## 15. Runtime evidence contract

Actual model success rowは、routeが生成できたという事実だけでruntime certificationにならない。

Provider/model certificationで必要な項目は別evidenceとしてload/input/inference/shape/finite/device/GPU/fallback/reload/hash identityを検証する。

## 16. Error semantics

Expected unsupported stateはterminal rowへ変換してcampaign全体のcoverageを保持する。

Unexpected data/protocol/output-integrity failureはfail closedする。

Output directory reuse、unknown game、invalid domain、non-finite target、duplicate/non-monotonic draw identity等を受け入れない。

## 17. Non-claims

この仕様が実装されていることは次を意味しない。

- real-data full catalog campaign completed
- all routes succeeded
- OOF improvement established
- Holdout evaluated
- Prospective evaluated
- champion selected
- promotion approved
