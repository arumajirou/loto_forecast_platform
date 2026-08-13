# Inventory Count Boundaries

```text
status_class: AUDITED_CURRENT_STATE
as_of: 2026-08-13T18:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: dfd9aa6e90b8bba4a18e1af70b566c80ddbf4c1b
```

This document exists because a library count of `1` can mean several different things in this repository. A Broad-v1 umbrella count must not be read as the number of models exposed by the upstream library, the number discovered at runtime, or the number already certified.

## 1. The four count classes

| Count class | Meaning |
|---|---|
| `Broad v1` | Frozen compatibility/scientific planning denominator used by the existing Broad campaign. It remains 174 total. |
| `Committed Expanded v2` | Versioned implementation identities currently emitted by `src/loto/models/implementation_catalog.py`. |
| `Observed / discovered denominator` | Runtime registry, source export, or operator-evidence denominator. It may be larger than the committed Expanded catalog and does not imply routability. |
| `Runtime-certified` | Exact identities with accepted load/input/inference/shape/finite/device/lifecycle evidence. It is never inferred from the other counts. |

Therefore:

```text
Broad count
!= committed Expanded count
!= discovered/source count
!= runtime-certified count
!= OOF-evaluated count
```

## 2. Current umbrella-library status

The current Expanded-v2 implementation code has completed only the AutoGluon decomposition. Other umbrella families remain one committed Expanded identity until their dedicated expansion issues are implemented and merged.

| Library | Broad v1 | Committed Expanded v2 now | Observed / discovered / evidence denominator | Interpretation |
|---|---:|---:|---|---|
| AutoGluon TimeSeries | 1 | **37** | 29 source models + 8 unique ensembles | Phase 1 merged; source-declared does not imply runtime-certified. |
| Darts | 1 | **1** | **58 public exports** currently documented; local NLinear/DLinear GPU evidence exists | #286 / TAJ-27 still open; 58 exports are not 58 certified standalone implementations. |
| GluonTS | 1 | **1** | Draft #309 records **18/18 lifecycle rows** across two isolated lanes | 18 is an execution-row denominator, not a unique model count; Expanded integration remains open. |
| ReservoirPy | 1 | **1** | final scientifically distinct expansion count not frozen | #294 expansion work remains open. |
| sktime | 1 | **1** | **141 discovered/importable**, including 53 core-compatible and 88 optional-dependency-declared; formal P1=4 | #289 / TAJ-32 still open; 141 is not 141 runtime-certified implementations. |
| skforecast | 1 | **1** | **18 operator-evidenced/planned candidate identities** can be distinguished from the current 0.23.0 evidence set | #289 / TAJ-32 still open; 18 is a planning/evidence denominator, not yet a committed Expanded-v2 count. |

## 3. Why skforecast still shows `1`

`src/loto/models/implementation_catalog.py` currently replaces only `autogluon-timeseries` with source-backed identities. Every other Broad-v1 row is copied unchanged into the Expanded-v2 catalog. Therefore the current committed Expanded-v2 count for `skforecast-recursive` remains one.

This is a real implementation gap, not only a README formatting problem.

GitHub #289 / Linear TAJ-32 explicitly requires the one-entry `sktime` and `skforecast` representations to be replaced with deterministic source/pinned-version implementation inventories while keeping Broad v1 frozen.

## 4. skforecast 0.23.0 planning/evidence denominator

`docs/SKFORECAST_RUNTIME_CERTIFICATION.md` currently distinguishes the following scientifically meaningful candidate identities. Wrapper × estimator Cartesian-product inflation is intentionally avoided.

| Group | Candidate identities counted |
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
| Foundation adapters: Chronos-2 / TimesFM 2.5 / Moirai-2 / TabICL v2 / TabPFN-TS / T0 | 6 |
| **Total candidate identities represented by the current evidence plan** | **18** |

Status boundaries within those 18 are mixed:

- many core/RNN/Chronos/TimesFM/TabICL lanes have operator-local PASS evidence;
- Moirai-2 normal dependency routability is BLOCKED even though an unsupported metadata-override probe ran;
- TabPFN-TS v3 inference is NOT_EXECUTED because checkpoint authentication/license access failed;
- T0 was not executed in the recorded skforecast sequence.

Thus `18` must not be rendered as `18 runtime-certified`.

## 5. Current derived inventory totals

```text
Broad v1                                      = 174
Probabilistic effective v1                    = 76
Combined Broad + Probabilistic accounting     = 250
Current Broad campaign plan                   = 174 × 6 = 1,044
Combined accounting × six games               = 250 × 6 = 1,500
Committed Expanded v2 Phase 1                 = 210
```

The current `210` is derived as:

```text
174 - AutoGluon umbrella 1 + AutoGluon implementations 37 = 210
```

It does not yet include the future Darts, GluonTS, ReservoirPy, sktime, skforecast, Time-Series-Library or BasicTS decompositions.

## 6. Display rule for README and dashboards

Do not use a single unlabeled `Count` column for umbrella libraries. Show at minimum:

```text
Broad v1
Committed Expanded v2
Observed/discovered denominator
Runtime status/evidence boundary
```

A reader should be able to see that `skforecast Broad=1` is a frozen compatibility identity while the current evidence already distinguishes 18 candidate implementation identities and the committed Expanded-v2 integration is still pending.

## 7. Scientific boundary

Inventory expansion is not forecast-skill evidence.

- primary metric remains Hit@±1;
- MAE/MSE/RMSE, position Hit@±1 and all-position Hit@±1 remain required;
- chronological Train/Validation/OOF and all configured seeds remain required;
- prediction SHA-256 sealing must precede actual reads;
- Holdout remains CLOSED;
- Prospective remains CLOSED;
- automatic promotion/retraining/registry writes remain FORBIDDEN.
