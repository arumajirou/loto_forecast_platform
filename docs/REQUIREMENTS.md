# 要件定義書

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

## 1. 目的

数字選択式くじ・digit gameを対象に、データ取得、特徴量生成、学習、HPO、評価、prediction sealing、runtime certification、Holdout/Prospective governance、promotion eligibilityまでを、再現可能かつ監査可能な研究基盤として提供する。

Canonical games:

```text
mini
loto6
loto7
bingo5
numbers3
numbers4
```

最重要目的は、見かけ上の最大精度やbest seedを作ることではなく、**同じeligible history・同じmetric・同じbaseline・全seed・明示protocol identityで比較可能な証拠を残すこと**である。

## 2. Game geometry要件

`loto.game.geometry`をgame shape/legalityの唯一の正本とする。

- select familyはstrict ascending / distinctを保持する。
- digits familyはposition orderとrepeated digitを保持する。
- game universe、positions、digit countを評価/decoder/provider側へ新規hard-codeしない。
- geometry-sensitive literalにはレビュー済み例外inventoryを使い、新規未審査hard-codeをgateで拒否する。

## 3. 最優先評価指標

Primary metricは **Hit@±1** とする。

必須併記:

- position Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE.

Geometry-general outcome metricはgame familyを尊重する。

- selectのhit count: set overlap;
- digitsのhit count: exact positional match;
- within-tau: position-wise absolute errorに基づく。

Digitsへset semanticsを適用して順序/重複を失ってはならない。

## 4. Mandatory baseline要件

同じeligible fold / target / seed policy / post-processing contractで最低限:

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

を常時比較する。

Baseline欠落を「比較完了」として扱わない。

## 5. Chronology / leakage要件

Formal ordering:

```text
Train
-> Validation / OOF development
-> authorized Holdout
-> sealed Prospective prediction
-> later actual scoring
```

必須:

- scaler/encoder/feature selector/calibrator/HPOはeligible Train内だけでfitする。
- target/future actualをprediction生成前に読み込ませない。
- missing/duplicate/order/domain/future-derived featureを検査する。
- raw sourceを上書きしない。
- Holdoutはdevelopment/OOF review前に開かない。
- Prospective predictionはfuture actualの利用前にimmutableに固定する。

## 6. Multi-seed要件

Approved seed inventoryを全て保持する。

最低限の集約:

```text
count
mean
population variance
standard deviation
minimum
maximum
worst value
worst seed
```

Best seedだけを採用根拠にしてはならない。

## 7. Prediction lock要件

各`game × candidate × seed`で:

```text
predict
-> persist actuals_known=false
-> durable write / fsync
-> SHA-256
-> only then read matching actual
-> score
```

既存run directoryは再利用しない。

## 8. Model capability要件

次の状態を分離する。

```text
REGISTERED
DEPENDENCY_DECLARED
IMPLEMENTED
SHARED_ROUTABLE
PROVIDER_ROUTABLE
RUNTIME_CERTIFIED
LOTTERY_COMPATIBLE
OOF_EVALUATED
HOLDOUT_EVALUATED
PROSPECTIVE_EVALUATED
PROMOTION_ELIGIBLE
```

Broad catalog countをruntime success countへ読み替えない。

現在のbroad forecast inventoryは174 entries、probabilistic platformは別に72-model catalogを持つ。両者は別surfaceとして管理する。

## 9. Unified all-model × all-game campaign要件

`uv run loto3 campaign`はrequested broad catalog × canonical game matrixをmaterializeする。

必須:

- each requested model × game pair exactly once;
- fail-visible statesを削除しない;
- six-game geometryに従う;
- seven baselines;
- primary Hit@±1 + required companion metrics;
- full seed inventory;
- prediction-before-actual sealing;
- new output directory;
- Holdout/Prospectiveを自動評価しない。

`matrix_complete=true`はcoverage completenessでありexecution success率100%ではない。

## 10. Shared / isolated execution要件

Shared execution:

```text
catalog.py
-> factory.py / workers.py
-> providers/**
```

Isolated execution:

```text
environments/**
*_campaign/**
adapters/**
scripts/run_*_provider.py
```

Model-specific dependency conflict、remote code、framework version pinがある場合はisolated laneを使用する。Root environmentへ無理に統合しない。

## 11. NeuralForecast AutoModel要件

Official AutoModel familyはOptuna/Ray backendを選択可能とする。

Result-affecting controlsを記録する。

- backend;
- search strategy;
- num samples/trials;
- CPUs/GPUs;
- parallel trials;
- precision;
- seed;
- refit policy;
- model-specific search/config identity.

Trial failureを消さず、best trialのみでall-model evidenceを置換しない。

## 12. Foundation/TSFM要件

Formal TSFM executionは最低限:

- canonical repo/model identity;
- immutable revision;
- artifact/snapshot identity;
- environment identity;
- provider route;
- load/inference/output evidence;
- effective device/fallback;

を記録する。

Broad catalogに`revision=None`がある場合、formal runはreviewed verified-revision manifestを別途bindする。推測SHAを埋めない。

## 13. Runtime certification要件

`import`やcatalog registrationだけでcertifiedにしない。

該当範囲で:

```text
load
input construction
inference
output shape
finite checks
requested/effective device
GPU PID / VRAM / utilization
CPU fallback
save/reload inference
cleanup / VRAM release
model/revision/environment/code/config hashes
```

を証拠化する。

Runtime certificationはforecast accuracyを証明しない。

## 14. Decoder要件

Probability-bearing candidate routeはdistribution identityを明示する。

Current bridge:

```text
row-normalized-slot-binary-probability-v1
```

- digits: positional window-mass WITHIN_TAU decode;
- select: ascending/distinct legality-constrained WITHIN_TAU DP;
- point-only routes: fake PMFを生成しない。

Decoder objective/distribution/post-processing identityをprotocol/runtime evidenceへ保存する。

## 15. Theory-aware threshold要件

Hit@±tau targetは次のsemanticsを持てること。

```text
absolute
excess_vs_iid_null
```

- game/tau-specific exact IID-null referenceを算出する。
- semanticsからimplied absolute targetを一意に導出する。
- implied targetが[0,1]外ならfail closedする。
- absolute targetがIID-null ceilingを超える場合、明示alternative hypothesisなしではfail closedする。
- IID-null ceilingを全てのbiased processに対する普遍的上限と表現しない。

## 16. Promotion eligibility要件

Historical v1 evidenceをv2としてsilent reinterpretしない。

Theory-aware v2は:

- gameを必須にする;
- current Hit@±1 promotion evidenceではtau=1固定;
- sealed Holdout/Prospective `game_id`とpolicy gameを一致させる;
- theory semanticsをabsolute thresholdへ解決する;
- aggregate/worst-window targetを確認する;
- Holdout→Prospective degradationを確認する;
- mandatory baselines全件を確認する。

Automatic actionは禁止:

```text
automatic_promotion=false
automatic_retraining=false
registry_write_allowed=false
```

全rule passでも最大自動decisionは`ELIGIBLE_FOR_HUMAN_APPROVAL`とする。

## 17. MDE / power planning要件

Target window実行前に、検出可能なeffect sizeを設計できること。

Current method:

```text
paired-score-normal-approximation-v1
```

最低限:

- alpha;
- target power;
- multiplicity;
- adjusted alpha;
- positive paired alternative;
- pre-target `score_sd`;
- required paired draws;
- minimum detectable effect;
- deterministic power curve.

Multiplicityには保守的Bonferroni planning alphaを使う。

Invalid effect, SD, draw count, alternative、`target_power <= adjusted_alpha`をfail closedする。

Power planning resultをp-value、Holdout result、promotion decisionとして扱わない。

## 18. Data/evidence persistence要件

各runにRun IDを持たせ、該当する範囲で:

```text
config
data hash
split hash
feature hash
code hash
Git commit
model/revision
seed inventory
predictions
actuals
metrics
logs
runtime/device evidence
protocol identity
prediction lock
artifact manifest
SHA256SUMS
```

を保存する。

PostgreSQL、DuckDB、Parquet、MLflow、OpenTelemetry等を利用してよいが、runごとのactual store/configをevidenceに残す。

## 19. Python/品質要件

基本構成:

```text
uv
pyproject.toml
uv.lock
src/
tests/
```

Quality gates:

- Ruff format/check;
- compileall;
- mypy where applicable;
- focused pytest during development;
- full pytest at final integration gate;
- exact-head/current-main CI before merge.

## 20. Scientific gate要件

```text
IMPLEMENTED
-> RUNTIME_CERTIFIED
-> OOF_EVALUATED
-> HOLDOUT_EVALUATED
-> PROSPECTIVE_EVALUATED
-> PROMOTION_ELIGIBLE
-> HUMAN APPROVAL
```

後段を前段から推測しない。

`NO_MODEL_BEATS_BASELINE`、`champion=null`を正常な結論として認める。

## 21. Current non-claims

このrequirementsの実装は次を自動的には意味しない。

- 174 entries全ての6ゲームruntime success;
- real-data 174 × 6 campaign完了;
- 72 probabilistic models全てのformal OOF完了;
- decoderのreal OOF improvement;
- lottery drawのnon-IID性;
- Holdout/Prospective完了;
- champion存在;
- production promotion完了。
