# データ契約 / Data Contract

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

## 1. 原則

- Raw dataは不変の正本として保存し、上書きしない。
- validated/canonical/features/evaluation artifactをrawと分離する。
- chronological identityを壊さない。
- future informationをTrain/OOFへ混入させない。
- data snapshotとresult-affecting splitをhashで識別可能にする。
- HoldoutとProspectiveはdevelopment dataから論理的・運用的に分離する。
- prediction evidenceは対応actualを読む前に固定する。

## 2. Canonical game targets

Target columnsは`loto.game.geometry`が定義するposition数に一致する。

| game | target columns | legal domain |
|---|---|---|
| `mini` | `n1..n5` | 1..31, strict ascending/distinct |
| `loto6` | `n1..n6` | 1..43, strict ascending/distinct |
| `loto7` | `n1..n7` | 1..37, strict ascending/distinct |
| `bingo5` | `n1..n8` | 1..40, strict ascending/distinct |
| `numbers3` | `n1..n3` | 0..9, ordered, repetition allowed |
| `numbers4` | `n1..n4` | 0..9, ordered, repetition allowed |

`draw_no`をchronological draw identityとして扱う。Formal data snapshotでは取得元のcanonical identityを保持する。

Digit rowsをsetへ変換してposition order/repetitionを失わない。

## 3. Unified campaign CSV contract

All-six-game input directory:

```text
mini.csv
loto6.csv
loto7.csv
bingo5.csv
numbers3.csv
numbers4.csv
```

最低限:

```text
draw_no,target columns...
```

Validation:

- required target columns present;
- `draw_no` integer-compatible;
- no duplicate `draw_no`;
- chronological ordering;
- numeric finite targets;
- `geometry.validate_outcome()` passes every row.

Invalid raw/canonical rowsをsilent clipして書き戻さない。

## 4. Time semantics

区別する時刻:

```text
event_time / draw occurrence
available_at / usable information time
ingested_at
forecast_created_at / seal time
actual_read_at
```

External featureはformal laneで原則:

```text
available_at <= forecast_created_at
```

対応actualはprediction seal後までscoring processへ渡さない。

## 5. Split contract

```text
Train / development folds
-> closed Holdout
-> Prospective
```

Unified campaignはconfigured Holdout tailをdevelopmentから除外し、Holdoutをscoreしない。

Development folds are chronological expanding/rolling folds with train indices strictly before test indices.

Prospective prediction is sealed before future actual availability/read.

## 6. Feature contract

Feature generation reads only eligible history preceding each target.

Train-only fitted components include as applicable:

```text
scaler
encoder
feature selection
calibration
learned baseline
HPO/search state
```

Candidate frequency/gap/recent-window features also use only pre-target history.

## 7. External data classification

```text
known_future
historical_only
static
prohibited_or_unverifiable
```

If availability time cannot be established and leakage risk cannot be bounded, exclude/quarantine the feature from formal evaluation.

## 8. Data identity / hashes

Formal runs retain at least applicable:

```text
source/acquisition origin
retrieval/ingestion timestamp
row count/schema identity
data snapshot SHA-256
split manifest SHA-256
feature manifest SHA-256
Git/code identity
protocol hash
```

`EvaluationProtocolV2` binds result-affecting data/split/feature identity.

## 9. Missing / duplicate / order policy

Fail closed or explicitly quarantine:

- duplicate draw identity;
- missing target;
- non-finite target;
- target outside legal domain;
- invalid select distinct/order;
- non-monotonic chronology;
- unknown game;
- future-derived feature evidence.

Do not impute a missing formal target actual and score against the imputation as if observed.

## 10. Raw immutability

Recommended layering:

```text
raw/             immutable source bytes
validated/       validation/quarantine
canonical/       normalized representation
features/        as-of derived features
artifacts/       model/evaluation evidence
```

Correction creates a new snapshot/version with lineage; it does not overwrite historical raw evidence.

## 11. Prediction data boundary

Prediction lock contains no target actual.

Minimum conceptual fields:

```text
actuals_known=false
prediction values
game/candidate/seed identity
protocol/runtime identity
created timestamp
SHA-256
```

Actual is joined only after sealing, by matching draw identity.

## 12. Theory/power data boundary

Theory reference calculations consume game geometry/model assumptions, not Holdout/Prospective actuals.

Pre-experiment `score_sd` used by power/MDE planning must come from allowed development/pilot evidence or a declared simulation fixed before the target window. It must not be estimated by looking ahead into the target Holdout/Prospective window and then represented as pre-planned evidence.

## 13. Promotion evidence data boundary

Theory-aware promotion v2 requires sealed score evidence carrying `game_id` on Holdout and every Prospective window. All scored-window game identities must match the policy game.

Historical v1 evidence is preserved under its original schema rather than silently rewritten.

## 14. Holdout / Prospective boundary

Development success does not automatically open Holdout.

Holdout actual/read evidence and Prospective actual/read evidence are separately authorized and recorded.

## 15. Non-claims

This contract does not claim every historical repository data file is already compliant. Each formal run must establish its own immutable data/split/protocol evidence.
