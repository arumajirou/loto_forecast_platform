# データ契約 / Data Contract

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T18:59+09:00
repository: arumajirou/loto_forecast_platform
audited_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
```

## 1. 原則

- Raw dataは不変の正本として保存し、上書きしない。
- validated/canonical/features/evaluation artifactをrawと分離する。
- chronological identityを壊さない。
- future informationをTrain/OOFへ混入させない。
- data snapshotとresult-affecting splitをhashで識別可能にする。
- HoldoutとProspectiveはdevelopment dataから論理的・運用的に分離する。

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

`draw_no`をchronological draw identityとして扱う。入力に無いsynthetic/dev utilityでは内部生成可能だが、正式data snapshotでは取得元のcanonical draw identityを保持する。

## 3. Unified campaign CSV contract

All-six-game runの標準入力directory:

```text
mini.csv
loto6.csv
loto7.csv
bingo5.csv
numbers3.csv
numbers4.csv
```

最低限各CSVは:

```text
draw_no,target columns...
```

を持つ。

Validation:

- required target columns present
- `draw_no` numeric/integer
- no duplicate `draw_no`
- strictly chronological ordering
- target numeric
- finite targets only
- geometry.validate_outcome passes every row

Invalid rowを黙ってclipしてraw/canonical inputへ書き戻さない。

## 4. Time semantics

利用可能なdata sourceでは次の概念を区別する。

- `event_time` / draw occurrence
- `available_at` / information became usable
- `ingested_at`
- `forecast_created_at`
- `actual_read_at` when relevant

External featureは原則:

```text
available_at <= forecast_created_at
```

を満たす必要がある。

対応drawのactualはprediction seal後までscoring processへ渡さない。

## 5. Split contract

Chronological split order:

```text
Train / development folds
-> Holdout
-> Prospective
```

Unified campaignはconfigured `holdout_size`の末尾sliceをdevelopmentから除外し、Holdoutを評価しない。

Development foldsはexpanding chronological rolling foldsを使い、test indexはtrain indexより後に限定する。

Prospective actualが未確定の状態で予測を封印する。

## 6. Feature contract

Feature生成は各target時点より前のeligible historyだけを読む。

Scaler、Encoder、feature selection、HPOのfit stateはTrain内だけから生成する。

Candidate bridgeで使用するfrequency/gap/recent-window featureもtarget indexより前のhistoryだけから計算する。

未来drawのtarget値をfeature generationへ渡してはならない。

## 7. External data classification

外生情報を使用する場合、最低限次へ分類する。

```text
known_future
historical_only
static
prohibited_or_unverifiable
```

Availability timestampが不明でleakage riskを解消できないfeatureはformal laneから除外またはquarantineする。

## 8. Data identity / hashes

正式runでは少なくとも次のidentityを保持する。

- source URI / acquisition origin when applicable
- retrieval/ingestion timestamp
- row count and schema identity
- data snapshot SHA-256
- split manifest SHA-256
- feature manifest SHA-256
- Git/code identity
- protocol hash

Unified campaignの`EvaluationProtocolV2`はdevelopment data/split/feature identityをresult-affecting protocolへbindする。

## 9. Missing / duplicate / order policy

次はfail closedまたは明示的quarantineとする。

- duplicate draw identity
- target missing
- non-finite target
- target outside legal domain
- select-game duplicate/non-ascending outcome
- non-monotonic chronology
- unknown game geometry
- future-derived feature evidence

Missing targetを予測対象actualとして補間してformal scoreへ使わない。

## 10. Raw immutability

Raw sourceをcanonical修正で上書きしない。

推奨layer:

```text
raw/             immutable bytes/source snapshot
validated/       validation result/quarantine
canonical/       normalized analytic representation
features/        derived as-of features
artifacts/       model/evaluation evidence
```

修正が必要な場合、新snapshot/versionを作りlineageを残す。

## 11. Prediction data boundary

Prediction lockはactual dataを含めない。

最低条件:

```text
actuals_known=false
prediction values
candidate/game/seed identity
protocol/runtime identity
created timestamp
SHA-256
```

Actualはseal後のscoring段階で対応draw identityを使ってjoinする。

## 12. Holdout / Prospective boundary

Development campaignの成功を理由にHoldoutを自動openしない。

Holdout actual/read evidenceとProspective actual/read evidenceは別gateで扱う。

## 13. Non-claims

このData Contractはrepository内の全歴史data fileが既に完全準拠であることを主張しない。正式runごとにdata audit/hashを実行し、そのrun evidenceで準拠を証明する。
