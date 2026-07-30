# Phase 0 Research: Primary-Source Model Inventory

**Date**: 2026-07-30. All retrievals against `main` unless noted.

## Why re-retrieve

The v2.1.0 catalog contained errors consistent with model-memory rather than retrieval: a
non-commercial TTM checkpoint, a gated repo recorded as available, and library counts that
summed to 85 against a stated total of 84. Every list below was therefore read from the
upstream `__all__` at retrieval time.

## Retrieved

| Source | Path | Result |
|---|---|---|
| Nixtla/neuralforecast | `neuralforecast/models/__init__.py` | **37** estimators |
| Nixtla/neuralforecast | `neuralforecast/auto.py` | **36** AutoModels (+`RayOptions`, `OptunaOptions` excluded) |
| Nixtla/statsforecast | `python/statsforecast/models.py` | **41** models |
| Nixtla/mlforecast | `mlforecast/auto.py` | **8** Auto estimators + `AutoMLForecast` |
| Nixtla/mlforecast | `mlforecast/lag_transforms.py` | 19 lag transforms |
| Nixtla/mlforecast | `mlforecast/target_transforms.py` | 10 target transforms |
| Nixtla/hierarchicalforecast | `hierarchicalforecast/methods.py` | **10** reconciliation methods |
| Hugging Face | `models?pipeline_tag=time-series-forecasting` | 806 models; top-30 by trending triaged |

Note: `statsforecast` sources live under `python/statsforecast/`, not `statsforecast/`. The
naive path returns 404 — worth recording because it is the kind of detail that silently becomes
"the library has no models" in an automated inventory.

## Gap against v2.1.0

| library | v2.1.0 | upstream | missing |
|---|---:|---:|---:|
| neuralforecast fixed | 17 | 37 | **20** |
| neuralforecast auto | 33 | 36 | **3** |
| statsforecast | 8 | 41 | **33** |
| mlforecast auto | 0 | 8 | **8** |
| hierarchicalforecast | 0 | 10 | **10** |
| | | | **74** |

## Newly registered names of consequence

**`SeasonalNaive`** — the reference against which nothing has beaten in this problem, and it was
absent from a 84-model catalog. Now a mandatory control.

**Croston family** (`CrostonClassic`, `CrostonOptimized`, `CrostonSBA`, `ADIDA`, `IMAPA`, `TSB`)
— intermittent-demand models. Per-number occurrence is an intermittent series by construction
(a given number appears in roughly `k/n` of draws), so this is the natural model class and the
entire family was missing.

**`ConformalSeasonalPool`** — upstream conformal prediction, complementing the platform's own
split-conformal implementation.

**`xLSTM` / `XLinear` / `SOFTSSharp`** and their Auto variants — three estimators added upstream
since the v2.1.0 snapshot.

**Reconciliation** — all ten methods. Enables coherence across the number → decade → parity →
total hierarchy, which no version of the platform had.

## TSFM triage

Registered 21 entries with `repo_id`. Notable corrections and additions:

| Decision | Reason |
|---|---|
| `ibm-granite/granite-timeseries-ttm-r2` replaces `ibm-research/ttm-r3` | r3 is non-commercial; r2 is Apache-2.0 |
| `google/timesfm-2.5-200m-transformers` preferred over `-pytorch` | transformers-native, no `trust_remote_code` |
| `amazon/chronos-2` added | 15.2M downloads, highest-usage TSFM, absent from v2.1.0 |
| `NX-AI/TiRex-2` added | successor to TiRex |
| `Datadog/Toto-Open-Base-1.0`, `Toto-2.0-4m` added | probabilistic, observability-domain pretraining |
| `AutonLab/MOMENT-1-{small,base,large}` added | general TS representation models |
| `ibm-granite/granite-timeseries-flowstate-r1` added | 9M params, smallest credible zero-shot forecaster |
| `time-series-foundation-models/Lag-Llama` added | probabilistic |
| `theforecastingcompany/t0-alpha` retained as `p2` | gated: weights resolve to zero bytes without accepted terms. Kept so the availability probe reports the block explicitly rather than the model appearing simply absent |

**All 21 carry `revision = None` / `revision_status = UNPINNED`.** Commit SHAs were not
retrievable in this environment and are not fabricated. `loto3 catalog --unpinned` lists them;
resolving them is a prerequisite for a reproducible `protocol_hash` over a TSFM sweep.

## Theoretical bounds re-derived

Order-statistic pmf `P(V_p = v) = C(v-1,p-1)·C(n-v,k-p)/C(n,k)`, computed in exact
`Fraction` arithmetic and asserted normalised per slot.

| game | MAE floor | MSE floor | ±1 ceiling | outcome space |
|---|---:|---:|---:|---:|
| mini | 3.8161 | 23.2000 | 0.2941 | 169,911 |
| loto6 | 4.9229 | 38.8571 | 0.2350 | 6,096,454 |
| loto7 | **3.8337** | 23.8571 | 0.2923 | 10,295,472 |
| bingo5 | 3.8708 | 24.3889 | 0.2895 | 76,904,685 |
| numbers3 | 2.5000 | 8.5000 | 0.3000 | 1,000 |
| numbers4 | 2.5000 | 8.5000 | 0.3000 | 10,000 |

The Loto7 MAE floor reproduces the independently known 3.8337 exactly, and every outcome space
matches the published jackpot odds — two independent checks that the geometry table is right.

A finding worth stating: the ±1-optimal predictor has **higher** MAE than the median predictor
(loto7: 4.0185 vs 3.8337), and the median predictor has **lower** ±1 rate than the ceiling
(0.2429 vs 0.2923). The two metrics cannot be jointly optimised, which is now asserted as a
test for every select game.
