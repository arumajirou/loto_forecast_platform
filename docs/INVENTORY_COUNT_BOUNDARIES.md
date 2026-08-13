# Inventory Count Boundaries

```text
status_class: AUDITED_CURRENT_STATE
as_of: 2026-08-13T18:30+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 770d5b972a9d7a9c983518f8b0cb144654b1ea24
```

この文書は、README等に表示される `1` が「そのライブラリに1モデルしかない」という意味に読めないよう、inventoryの分母を分離するためのcurrent-state資料です。

## 1. countの種類

| Count class | 意味 |
|---|---|
| `Broad v1` | 既存Broad campaignとの互換性のため凍結されたcanonical identity数。総数174は変更しない。 |
| `Committed Expanded v2` | `src/loto/models/implementation_catalog.py` が現在実際に返すversioned implementation identity数。 |
| `Observed / discovered denominator` | runtime registry、source export、operator evidenceなどから確認できる別分母。routability/runtime成功を意味しない。 |
| `Runtime-certified` | exact identityでload/input/inference/shape/finite/device/lifecycle等の受理済み証拠を持つ数。 |

```text
Broad count
!= committed Expanded count
!= discovered/source count
!= runtime-certified count
!= OOF-evaluated count
```

## 2. umbrella libraryの現在値

現在のExpanded-v2実装コードでumbrellaの分解が完了しているのはAutoGluon Phase 1です。その他はBroad identityをそのままExpanded側へコピーしているため、committed Expanded count自体はまだ1です。

| Library | Broad v1 | Committed Expanded v2 | Observed / discovered / evidence denominator | 現在の解釈 |
|---|---:|---:|---|---|
| AutoGluon TimeSeries | 1 | **37** | 29 source models + 8 unique ensembles | Phase 1 merged。source-declared != runtime-certified。 |
| Darts | 1 | **1** | **58 public forecasting exports**をPhase 2で調査中。local NLinear/DLinear GPU evidenceあり | #286 / TAJ-27 open。58全件standalone/runtime-certifiedではない。 |
| GluonTS | 1 | **1** | **9 current-main P6 estimator algorithms**、2 isolated lanesで18 lifecycle cells | PR #315でREADME表示修正済み。#288/#309のExpanded/runtime gateは別。 |
| ReservoirPy | 1 | **1** | scientifically distinct expansion count未freeze | #294 open。 |
| sktime | 1 | **1** | **141 discovered/importable** = 53 core-compatible + 88 optional-dependency-declared、formal P1=4 | #289 / TAJ-32 open。141 != 141 runtime-certified。 |
| skforecast | 1 | **1** | current 0.23.0 operator evidenceから **18 candidate implementation identities** を科学的に区別可能 | #289 / TAJ-32 open。18はplanning/evidence denominatorで、まだcommitted Expanded countではない。 |

## 3. なぜskforecastがまだ1なのか

`src/loto/models/implementation_catalog.py` のcurrent implementationは `autogluon-timeseries` だけを37 identitiesへ置き換えています。それ以外のBroad-v1 rowはExpanded-v2へそのままコピーされます。

したがって現在のコードでは次が事実です。

```text
skforecast Broad v1                 = 1
skforecast committed Expanded v2    = 1
skforecast evidence/planning slots  = 18
```

これはREADMEだけの表示不具合ではなく、**#289 / TAJ-32の実装がまだ完了していないことを示す実装gap**です。

## 4. skforecast 0.23.0の18 candidate identities

`docs/SKFORECAST_RUNTIME_CERTIFICATION.md` のcurrent evidence planを、wrapper × estimatorの無意味なCartesian productを避けて数えると以下です。

| Group | Count |
|---|---:|
| recursive Ridge | 1 |
| recursive HistGradientBoosting | 1 |
| recursive external boosters: LightGBM / XGBoost / CatBoost | 3 |
| direct Ridge | 1 |
| recursive multi-series Ridge | 1 |
| direct multivariate Ridge | 1 |
| EquivalentDate baseline | 1 |
| Stats ARAR | 1 |
| RNN LSTM / GRU | 2 |
| Foundation: Chronos-2 / TimesFM 2.5 / Moirai-2 / TabICL v2 / TabPFN-TS / T0 | 6 |
| **Total candidate identities represented by the current evidence plan** | **18** |

18の内部statusは同一ではありません。

- core / RNN / Chronos-2 / TimesFM 2.5 / TabICLにはoperator-local PASS evidenceがある。
- Moirai-2はunsupported dependency metadata override下ではruntimeが通るがnormal routabilityはBLOCKED。
- TabPFN-TS v3はauthentication/license gateでcheckpoint取得前に停止しinference NOT_EXECUTED。
- T0はこのskforecast-specific sequenceでは未実行。

したがって `18` を `18 runtime-certified` と表示してはいけません。

## 5. current totals

```text
Broad v1                                      = 174
Probabilistic effective v1                    = 76
Combined Broad + Probabilistic accounting     = 250
Current Broad campaign plan                   = 174 × 6 = 1,044
Combined accounting × six games               = 250 × 6 = 1,500
Committed Expanded v2 Phase 1                 = 210
```

current `210` は次から導出されます。

```text
174 - AutoGluon umbrella 1 + AutoGluon implementations 37 = 210
```

Darts、GluonTS、ReservoirPy、sktime、skforecast、Time-Series-Library、BasicTSの今後の分解はまだこの210へ入っていません。

## 6. README/dashboard display rule

umbrella libraryには単一の無印 `Count` を使わず、少なくとも次を分離します。

```text
Broad v1
Committed Expanded v2
Observed/discovered denominator
Runtime/evidence boundary
```

特に `skforecast=1` は「Broad互換identityが1」であり、「skforecastに1モデルしかない」という意味ではありません。

## 7. Scientific boundary

Inventory expansionはforecast skillではありません。

- primary metric: Hit@±1
- companions: MAE/MSE/RMSE、position Hit@±1、all-position Hit@±1
- chronological Train/Validation/OOF
- all configured seeds + mean/variance/worst
- actual read前のprediction SHA-256 seal
- Holdout=CLOSED
- Prospective=CLOSED
- automatic promotion/retraining/registry write=FORBIDDEN
