# Current Change Summary

```text
status_class: AUDITED_CURRENT_STATE
as_of: 2026-08-13T18:10+09:00
repository: arumajirou/loto_forecast_platform
audit_base_main: 0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d
latest_merged_boundary: PR #313
```

この資料は、現在の実装と主要改修を「何が変わったか」「どこまで証拠があるか」で追うための短い入口です。Git履歴や個別PR、詳細モデル表の代替ではありません。

## 1. 現在の全体像

現在のrepositoryには少なくとも次が実装されています。

- 6 canonical game geometries;
- frozen Broad v1 **174 identities**;
- effective Probabilistic v1 **76 identities**;
- Broad + Probabilisticのcombined accounting denominator **250**;
- current Broad campaign planner **174 × 6 = 1,044** units;
- combined accountingでのsix-game denominator **250 × 6 = 1,500** units;
- Expanded v2 Phase 1 **210 implementation identities**;
- fail-visible model×game execution rows;
- resource-aware scheduler / GPU assignment / timeout cleanup / resume fingerprint;
- game-parallel campaign executionとlive progress;
- dynamic scikit-learn discovery/smoke/certification;
- XGBoost/CatBoost GPU routingとLightGBM OpenCL GPU routing;
- prediction sealing、Hit@±1-first evaluation、mandatory baselines、multi-seed summary;
- repository observability / dashboard / operations control center;
- StatsForecast / NeuralForecast / AutoGluon / sktime / skforecast / Darts / GluonTS / TSFM等のlibrary別provider・runtime evidence surface。

重要な分母訂正:

```text
Broad v1                              = 174
Probabilistic effective v1            = 76
Combined Unified accounting           = 250
Current `loto3 campaign` planner      = 174 × 6 = 1,044
Combined accounting × six games       = 250 × 6 = 1,500
```

**current `loto3 campaign --plan-only` が1,500行を生成するわけではありません。** current plannerはBroad 174を対象にします。Probabilistic 76は別surfaceです。

---

## 2. 評価・科学ガバナンス

Primary metric:

```text
Hit@±1
```

必須併記:

```text
MAE
MSE
RMSE
position-wise Hit@±1
all-position Hit@±1
```

必須baseline:

```text
Random
fixed
mean
median
last / recent
frequency
statistical
```

科学順序:

```text
Train
-> Validation / development OOF
-> explicit Holdout authorization
-> Holdout
-> explicit Prospective protocol
-> sealed future prediction
-> later actual scoring
-> promotion eligibility
-> HUMAN APPROVAL
```

Scaler / Encoder / feature selection / HPOは許可されたTrain内のみでfitします。複数seedを残し、mean / variance / worstを保存します。予測はactual参照前にSHA-256 + timestampで固定します。

```text
Holdout=CLOSED
Prospective=CLOSED
Automatic promotion/retraining/registry writes=FORBIDDEN
Champion=NOT_AUTHORIZED_BY_CURRENT_EVIDENCE
```

---

## 3. 実行基盤の主要改修

| PR | 主な変更 | 現在の意味 |
|---|---|---|
| #270 | runtime evidence serialization + resource-aware broad runner | runtime evidenceとresource制約の保持 |
| #277 | resume fingerprint / physical GPU assignment / process-tree cleanup / outer worker cap | 安全な再開・GPU割当・timeout cleanup |
| #302 | process-parallel six-game Broad campaign wrapper + live progress | game単位並列・progress/aggregate artifacts |
| #304 | XGBoost/CatBoost GPU lease routing | scheduler GPU leaseをmodel constructor/runtimeへ接続 |
| #305 | LightGBM accelerator probe | current buildのCUDA tree learnerをfail-closed、OpenCL GPUを実測 |
| #306 | LightGBM OpenCL GPU routing | verified OpenCL contractをcandidate/position workerへ接続 |

並列化・GPU routingはplatform capabilityであり、全モデルruntime successや精度優位を意味しません。

---

## 4. Inventory / model surfaceの主要改修

### Broad v1

Broad v1は**174**で凍結されています。`src/loto/models/catalog_full.py`の`build_catalog()` / `catalog_counts()`がcountを計算し、READMEだけを正本にしません。

### Probabilistic v1 / combined accounting

current loaderはcatalog sourceに不足しているPPL-02 4 identitiesを補います。effective probabilistic denominatorは**76**です。

ただし、current Broad campaign plannerへ76 identitiesが自動連結されるわけではありません。

### Expanded v2

PR #293はBroadを変更せず、別のExpanded v2 inventoryを導入しました。Phase 1はAutoGluon umbrella 1件を29 source models + 8 unique ensemblesへ展開し、**210 implementation identities**を構成します。

### Dynamic scikit-learn

PR #301で`loto-sklearn`を追加し、installed-versionの`all_estimators()`を使うdynamic inventory / smoke / certification surfaceをBroad 174とは別に実装しました。

---

## 5. Library別の重要な現在値

### StatsForecast / NeuralForecast / MLForecast

shared/provider/Auto execution surfacesと部分runtime evidenceがあります。inventory countを全モデル×全ゲームruntime完走と読み替えません。

### AutoGluon

Expanded v2 Phase 1に37 source-backed identitiesがあります。source declarationとruntime certificationは別です。

### sktime

current bounded evidence:

```text
sktime=1.0.1
registry discovered/importable=141
core compatible=53
optional dependency declared=88
formal P1 models=4
formal P1 result=4/4 PASS
```

141はruntime-certified denominatorではありません。

### skforecast

PR #310でskforecast 0.23.0のmaintainer-host evidenceを`OPERATOR_LOCAL_EVIDENCE`として分離記録しました。

主なbounded evidence:

- recursive/direct/multi-series/multivariate/statistical/backtesting/persistence;
- RNN LSTM/GRU actual CUDA + CPU fallback;
- Chronos-2 GPU/CPU;
- TimesFM 2.5 GPU/CPU;
- TabICL runtime + checkpoint identity/hash;
- Moirai-2 compatibility override boundary;
- TabPFN-TS authentication/license block。

#289 / TAJ-32のcurrent-main Expanded v2 inventory/routingは別gateです。

### Darts

PR #311で古い`REAL_DARTS_RUNTIME_BLOCKED`表現が是正されました。current mainにはprovider/campaign foundationがあり、別のlocal exact-worktreeでは:

```text
torch=2.9.1+cu130
CUDA=13.0
pytorch-lightning=2.6.5
official bootstrap=PASS
NLinear actual GPU fit/predict=VERIFIED
DLinear actual GPU fit/predict=VERIFIED
```

ただしこれは`LOCAL_VERIFIED / MAIN_PENDING`です。#286 / TAJ-27はsource-complete Expanded v2 inventory/routing/formal smokesのため継続中です。

### GluonTS

Draft PR #309 exact head:

```text
edba730a4f2c944c1ccc0bee510f7ce34833b6c3
```

bounded exact-head evidence:

```text
latest lane=9/9 VERIFIED
compat lane=9/9 VERIFIED
total lifecycle=18/18 VERIFIED
observed_devices=['cpu']
P7D_RC=0
VERIFY_RC=0
FORMAL_RC=0
evidence_state=VALID
certification_status=VERIFIED
verification_state=VERIFIED
p8_eligible=true
```

しかしPR #309はDraft/openでmain未統合です。GitHub `ci` / `windows-portability-ci`もこのdocumentation audit時点ではqueuedのため、`CURRENT_MAIN_RUNTIME_CERTIFIED`とは表現しません。

---

## 6. Repository observability / operations

| PR | 改修 |
|---|---|
| #273 | repository observability dashboard / structured intake |
| #274 | evidence-aware visual dashboard / Pages gate |
| #276 | repository operations control center / workflow classification |

`queued`、`cancelled`、zero-step jobをPASSへ変換しません。コード/テストfailureとrunner/pre-run/billing/unrelated-main failureは別分類します。

---

## 7. Documentation alignment履歴

| PR | 内容 | Merge SHA |
|---|---|---|
| #299 | implementation-grounded README audit | `05eba49dad8c0700c303783267784cfde081e419` |
| #300 | library/model compatibility matrix | `a7eb50ca534c4880681d5febab193b0c2692f50c` |
| #308 | README current-state reconciliation | `932977f7c4d8b4673c2bb02a23ec4ba6b7ad85bf` |
| #310 | current-state docs + skforecast operator evidence | `4f4f8579c6bcc05e25ea472e48385114bb56c71d` |
| #312 | detailed library/model matrix alignment | `063120fd9b07d07548442edbce480a6d068f9f43` |
| #311 | Darts evidence + Broad planner boundary correction | `9623f2a562d21b4f9be84c392429885a51a72fe1` |
| #313 | README audit-boundary stabilization after #311 | `0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d` |

PR numberingとmerge時系列は一致しない場合があります。current main / merge SHAが正本です。

---

## 8. Major open gates

| Gate | Current boundary |
|---|---|
| #265 / #266 | complete Broad/runtime accounting campaigns remain incomplete |
| #286 / TAJ-27 | Darts Expanded v2 source-complete inventory/routing in progress |
| #288 / TAJ-29 | GluonTS Expanded v2; Draft #309 has bounded exact-head CPU evidence but main-pending |
| #289 / TAJ-32 | sktime + skforecast Expanded v2 completion |
| #292 / TAJ-36 | final Expanded v2 freeze + full six-game runtime certification |
| #297 | Toto 22M native-Linux external GPU PID/VRAM/release evidence |
| #281 / TAJ-30 | TabPFN-TS-3 authentication/license/runtime gate |
| #272 | native Windows path portability |
| #239 | Timer Base 84M development OOF |
| #118 | Timer-S1 continuation |
| #275 | GitHub Pages activation |

Live GitHub/Linear state is authoritative when it changes after this snapshot.

---

## 9. まだ成立していない主張

Current evidence does **not** establish:

- all Broad 174 models succeeding on all six games;
- a single current campaign invocation executing Broad 174 + probabilistic 76 automatically;
- final Expanded v2 count/runtime completion;
- all registered models as routable;
- all routable models as runtime-certified;
- universal GPU execution;
- all-model development OOF superiority;
- Holdout completion;
- Prospective completion;
- champion selection;
- production promotion.

Current claims should be checked against `README.md`, `docs/STATUS.md`, `docs/CURRENT_VERIFICATION_REPORT.md`, `docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md`, and live GitHub/Linear state.
