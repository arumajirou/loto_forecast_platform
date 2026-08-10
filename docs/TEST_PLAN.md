# テスト計画書 / Test Plan

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T18:59+09:00
repository: arumajirou/loto_forecast_platform
audited_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
```

## 1. 目的

本計画は、implementation correctness、data leakage resistance、runtime integrity、scientific evaluation integrity、cross-platform packagingを分離して検証する。

「testが通った」をruntime certificationやforecast accuracyへ読み替えない。

## 2. 実装中の基本順序

変更中は対象testとsmokeを優先する。

```text
focused unit/contract test
-> focused smoke
-> Ruff/compile/type where relevant
-> affected integration test
-> full pytest
-> GitHub CI / portability
```

重いfull pytestを小変更ごとに反復せず、実装がまとまった最終gateで実行する。

## 3. Commit-level tests

最低限:

- Pydantic/contract validation
- canonical geometry legality
- feature causality / no-future access
- decoder invariants
- prediction-lock serialization/integrity
- metric calculation
- seed aggregation
- output shape/finite checks
- output directory immutability

## 4. Unified campaign focused tests

必須coverage:

### 4.1 Plan completeness

`build_campaign_plan`がrequested broad catalog × known gamesのcardinality/uniquenessを満たす。

### 4.2 Six-game baseline matrix

各canonical gameで7 mandatory baselineを実行し、required metricsとprediction sealを生成する。

### 4.3 Candidate bridge

少なくともdigit familyとselect familyの双方でcandidate estimatorがshared routeを通る。

### 4.4 Fail-visible states

Reconciliation-only、unsupported、non-routable等をmatrixから削除せずterminal statusとして保持する。

### 4.5 Seed summary

全configured seedを保持し、mean、population variance、std、min/max、worst value/seedを検証する。

### 4.6 Prediction lock ordering

Lock artifactの`actuals_known=false`、non-empty predictions、SHA-256 evidence、single-use outputを検証する。

## 5. Decoder tests

### 5.1 Select MAP compatibility

Historical MAP APIとlegal constrained outputを保持する。

### 5.2 WITHIN_TAU optimality

Reduced geometryでbrute-force optimumと一致すること。

### 5.3 IID-null exact cases

mini/loto6/loto7/bingo5などの既知geometryで理論的fixtureに対する期待optimumを検証する。

### 5.4 Digit decoder

Crafted probability surfaceでMAPとWITHIN_TAU/window-mass decisionが意図通り異なることを検証する。

### 5.5 Unified routing

Numbers3等digit gameはdigit WITHIN_TAU、Loto7等select gameはconstrained WITHIN_TAUを使うこと。

### 5.6 Point-only route

Point-only workerへ架空のprobability distributionを生成しないこと。

### 5.7 Fail closed

Non-finite、negative、invalid shape、zero-mass等のinvalid probability入力を拒否する。

Decoder theory testは実データOOF improvement testではない。

## 6. Data contract tests

- required target columns
- draw identity uniqueness
- chronological monotonicity
- finite numeric targets
- geometry legality
- future information sentinel
- raw immutability where workflow applies
- development/holdout split separation

## 7. Metrics tests

Game geometryに応じて:

- Hit@±1
- per-position Hit@±1
- all-position Hit@±1
- MAE
- MSE
- RMSE

を検証する。

Select-only set/ranking metricがdigit gamesへ誤適用されないことも検証する。

## 8. Runtime certification tests

Runtime certification対象ではunit testだけで成功扱いしない。

該当model/providerごとに:

- dependency import
- model load
- input construction
- inference
- output shape
- finite values
- requested/observed device
- GPU PID/VRAM when CUDA claimed
- CPU fallback behavior
- save/reload inference when required

をsmoke/certification artifactとして検証する。

## 9. Dependency/packaging CI

### Linux standard CI

Repository standard gate:

```text
locked dependency install
Ruff format check
Ruff lint
compileall
full pytest
clean-tree verification
```

### Native Windows portability

最低限:

```text
universal lock validation
dependency resolution
wheel build
installed-wheel import
tracked-file cleanliness
```

Queued/cancelled jobをPASSと記録しない。

## 10. Pull Request merge gate

Merge前に:

- current main SHA再取得
- PR base/head SHA再取得
- ahead/behind確認
- changed-file scope確認
- mergeable/draft state確認
- exact-head/current-main CI確認
- unresolved review threads確認
- security/runtime-sensitive path確認
- expected-head guard使用

Dependency PRでlockが重なる場合はserial mergeし、残りをrebase/recreateして再検証する。

## 11. Scientific evaluation tests

Formal OOF campaignでは:

- chronological folds
- mandatory baselines
- full seed inventory
- leakage checks
- prediction seal before actual read
- metric aggregation
- worst-seed retention
- protocol/data/code hashes

を検証する。

Best seedのみのsuccess testをformal acceptanceにしない。

## 12. Holdout gate tests

Holdoutはdevelopment/OOF承認後のみ。

最低限:

- immutable Holdout identity
- Holdout actual unopened before authorization
- pre-existing prediction/protocol evidence
- no retuning on Holdout
- required metrics/baselines
- result registration

を確認する。

## 13. Prospective gate tests

- prediction created before future actual exists/is read
- timestamp/hash seal
- immutable prediction artifact
- later actual ingestion separated
- scoring reproducible
- all-seed/baseline comparison where protocol requires

## 14. Promotion tests

Promotion/Champion認定は別gateであり、最低限:

- approved OOF evidence
- approved Holdout evidence
- required Prospective evidence
- runtime certification
- artifact/config/code/data identity
- policy/approval state

を満たす。

`champion=null` を正常結果として扱う。

## 15. Current non-claims

このtest planの存在やCI successだけでは:

- full real-data 174 × 6 campaign success
- decoder real OOF improvement
- Holdout success
- Prospective success
- promotion

を証明しない。
