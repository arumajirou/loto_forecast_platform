# Inventory Count Boundaries

```text
status_class: AUDITED_CURRENT_STATE
as_of: 2026-08-13T20:30+09:00
repository: arumajirou/loto_forecast_platform
phase3_base_main_sha: eb988d2947994bb637dc8f0cbc40afa05570027f
```

この文書は、README等に表示される `1` が「そのライブラリに1モデルしかない」という意味に読めないよう、inventoryの分母を分離するためのcurrent-state資料です。

## 1. countの種類

| Count class | 意味 |
|---|---|
| `Broad v1` | 既存Broad campaignとの互換性のため凍結されたcanonical identity数。総数174は変更しない。 |
| `Committed Expanded v2` | `src/loto/models/implementation_catalog.py` が実際に返すversioned implementation identity数。 |
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

Expanded v2はAutoGluonに続いてGluonTS P6 registryもsource-backed implementation identityへ分解します。Broad v1は変更しません。

| Library | Broad v1 | Committed Expanded v2 after Phase 3 | Observed / discovered / evidence denominator | 現在の解釈 |
|---|---:|---:|---|---|
| AutoGluon TimeSeries | 1 | **37** | 29 source models + 8 unique ensembles | source-declared != runtime-certified。 |
| Darts | 1 | **1** | **58 public forecasting exports**をPhase 2で調査中。local NLinear/DLinear GPU evidenceあり | #286 / TAJ-27 open。58全件standalone/runtime-certifiedではない。 |
| GluonTS | 1 | **9** | **9 P6 estimator algorithms**、2 isolated lanesで18 lifecycle cells | #288 inventory integration。18はunique model countではない。#309 runtime repairはmain pending。 |
| ReservoirPy | 1 | **1** | scientifically distinct expansion count未freeze | #294 open。 |
| sktime | 1 | **1** | **141 discovered/importable** = 53 core-compatible + 88 optional-dependency-declared、formal P1=4 | #289 / TAJ-32 open。141 != 141 runtime-certified。 |
| skforecast | 1 | **1** | current 0.23.0 operator evidenceから **18 candidate implementation identities** を科学的に区別可能 | #289 / TAJ-32 open。18はplanning/evidence denominatorで、まだcommitted Expanded countではない。 |

## 3. GluonTSの1 / 9 / 18

```text
GluonTS Broad v1 canonical identity  = 1 (`gluonts-deepar`)
GluonTS Expanded v2 implementations  = 9
GluonTS P6 lifecycle cells            = 9 × 2 isolated lanes = 18
```

Expanded v2の9 identityは`src/loto/adapters/gluonts/p6_registry.py`から導出し、`src/loto/models/implementation_catalog.py`でlibrary-specific implementation identityへ変換します。

```text
gluonts-torch-deepnpts
gluonts-torch-deepar
gluonts-torch-tide
gluonts-torch-simplefeedforward
gluonts-torch-temporalfusiontransformer
gluonts-torch-wavenet
gluonts-torch-dlinear
gluonts-torch-patchtst
gluonts-torch-lagtst
```

9 identityの初期runtime stateは`NOT_RUN` / `runtime_certified=false`です。Draft #309 exact-headで18/18 CPU lifecycle VERIFIEDでも、その証拠をcurrent-main inventoryへ自動昇格させません。

## 4. なぜskforecastがまだ1なのか

Phase 3後の`implementation_catalog.py`はAutoGluonとGluonTSのBroad umbrellaを分解しますが、skforecast Broad rowはまだExpanded-v2へそのままコピーされます。

```text
skforecast Broad v1                 = 1
skforecast committed Expanded v2    = 1
skforecast evidence/planning slots  = 18
```

これはREADMEだけの表示不具合ではなく、**#289 / TAJ-32の実装がまだ完了していないことを示す実装gap**です。

## 5. skforecast 0.23.0の18 candidate identities

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

## 6. current totals

```text
Broad v1                                      = 174
Probabilistic effective v1                    = 76
Combined Broad + Probabilistic accounting     = 250
Current Broad campaign plan                   = 174 × 6 = 1,044
Combined accounting × six games               = 250 × 6 = 1,500
Expanded v2 Phase 1                           = 210
Expanded v2 after GluonTS Phase 3             = 218
```

Phase 1:

```text
174 - AutoGluon umbrella 1 + AutoGluon implementations 37 = 210
```

Phase 3 current implementation:

```text
174
- AutoGluon umbrella 1
- GluonTS umbrella 1
+ AutoGluon implementations 37
+ GluonTS implementations 9
= 218
```

`expanded_inventory_counts()`が218を導出し、手書き値をcount authorityにしません。

Darts、ReservoirPy、sktime、skforecast、Time-Series-Library、BasicTSの今後の分解はまだ218へ入っていません。したがって218はExpanded v2の最終freeze値ではありません。

## 7. README/dashboard display rule

umbrella libraryには単一の無印 `Count` を使わず、少なくとも次を分離します。

```text
Broad v1
Committed Expanded v2
Observed/discovered denominator
Runtime/evidence boundary
```

特に`GluonTS=1`はBroad互換identity、`GluonTS=9`はExpanded implementation identity、`18`は2 laneのlifecycle cell数です。

## 8. Scientific boundary

Inventory expansionはforecast skillではありません。

- primary metric: Hit@±1
- companions: MAE/MSE/RMSE、position Hit@±1、all-position Hit@±1
- chronological Train/Validation/OOF
- all configured seeds + mean/variance/worst
- actual read前のprediction SHA-256 seal
- Holdout=CLOSED
- Prospective=CLOSED
- automatic promotion/retraining/registry write=FORBIDDEN
