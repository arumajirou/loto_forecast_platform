# Model and library execution matrix

```text
status_class: AUDITED_REFERENCE
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
```

## 1. Purpose

この資料は**モデル名の在庫ではなく、どのsurfaceが実際にroute/load/execute/certifyできるか**を整理する。

```text
registered != routable != runtime-certified != lottery-compatible != OOF-evaluated != promoted
```

## 2. Model surfaces

| Surface | Source | Meaning |
|---|---|---|
| Broad forecast inventory | `src/loto/models/catalog_full.py` | 174-entry planning inventory |
| Shared execution catalog | `src/loto/models/catalog.py` | normal `ModelSpec` selection boundary |
| Shared candidate runtime | `models/factory.py` | in-process candidate estimators |
| Shared position/foundation runtime | `models/workers.py` | position-series/foundation dispatch |
| Shared foundation registry | `models/providers/registry.py` | concrete provider classes |
| Isolated campaigns/providers | `*_campaign/**`, `adapters/**`, `environments/**` | version/provider-specific execution |
| Probabilistic platform | `probabilistic/**` | separate 72-model catalog and runner |
| Runtime audit | `audit/**` | point-in-time exact identity evidence |

## 3. CLI boundaries

| Command | Catalog/runtime source | Use |
|---|---|---|
| `uv run loto3 catalog --counts` | `catalog_full` | broad inventory |
| `uv run loto3 catalog --library ...` | `catalog_full` | broad library filter |
| `uv run loto models list` | `catalog.py` | shared execution specs |
| `uv run loto models show ID` | `catalog.py` | one shared spec |
| `uv run loto experiment research --config ...` | `orchestration/research.py` + shared catalog | older shared research path |
| `uv run loto3 research ...` | `orchestration/research_v3.py` | separate instrumented research cycle |
| `uv run loto3 campaign ...` | broad planning + compatible shared routes | canonical six-game development campaign |
| `uv run loto3 probabilistic ...` | probabilistic catalog/runner | Bayesian/probabilistic platform |

The two research commands and the unified campaign are not interchangeable.

## 4. Broad inventory counts

| Library | Count |
|---|---:|
| builtin | 4 |
| sklearn | 7 |
| lightgbm | 2 |
| xgboost | 1 |
| catboost | 1 |
| statsforecast | 41 |
| neuralforecast | 37 |
| neuralforecast_auto | 36 |
| mlforecast_auto | 8 |
| hierarchicalforecast | 10 |
| tsfm | 21 |
| autogluon | 1 |
| darts | 1 |
| gluonts | 1 |
| sktime | 1 |
| skforecast | 1 |
| reservoirpy | 1 |
| **total** | **174** |

This count is computed inventory, not executable-success evidence.

## 5. Direct candidate estimators

Shared candidate IDs:

| ID | Library/class | Dependency lane | Capabilities |
|---|---|---|---|
| `uniform` | builtin UniformCandidateAdapter | core | control/probability |
| `frequency` | builtin FrequencyCandidateAdapter | core | probability/ranking |
| `logistic` | sklearn LogisticRegression | core | probability/exogenous |
| `random-forest` | sklearn RandomForestClassifier | core | probability/exogenous |
| `extra-trees` | sklearn ExtraTreesClassifier | core | probability/exogenous |
| `hist-gradient-boosting` | sklearn HistGradientBoostingClassifier | core | probability/exogenous |
| `lightgbm-classifier` | LightGBM LGBMClassifier | full | probability/ranking/exogenous |
| `xgboost-classifier` | XGBoost XGBClassifier | full | probability/exogenous |
| `catboost-classifier` | CatBoost CatBoostClassifier | full | probability/exogenous |

Position IDs additionally include `ridge-position`, `elasticnet-position`, `lightgbm-position`.

`RuntimeModel` removes identity/target fields from model features and normalizes estimator outputs into candidate probabilities/scores.

## 6. StatsForecast

Broad inventory: **41 classes** including AutoARIMA, AutoETS, AutoCES, AutoTheta, ARIMA, AutoRegressive, smoothing/Holt families, baseline families, intermittent-demand models, MSTL/MFLES/TBATS, Theta variants, GARCH/ARCH and UCM.

Shared explicit IDs:

```text
stats-naive
stats-historic-average
stats-autoarima
stats-autoets
stats-autotheta
stats-autoces
stats-croston
stats-tsb
```

Ordinary position-series route imports `statsforecast.models.<class>`, fits `StatsForecast` and predicts h=1. Croston/TSB use candidate-series representation.

**41 broad registrations do not mean 41 shared IDs.**

## 7. MLForecast

Broad AutoMLForecast inventory:

```text
AutoLightGBM
AutoXGBoost
AutoCatboost
AutoLinearRegression
AutoRidge
AutoLasso
AutoElasticNet
AutoRandomForest
```

Direct shared IDs:

```text
mlforecast-ridge
mlforecast-lightgbm
```

The shared worker builds lag features and predicts one step with Ridge or LightGBM.

## 8. NeuralForecast fixed models

Broad official fixed inventory: 37.

```text
RNN GRU LSTM TCN DeepAR DilatedRNN MLP NHITS NBEATS NBEATSx
DLinear NLinear TFT VanillaTransformer Informer Autoformer PatchTST
FEDformer StemGNN HINT TimesNet TimeLLM TSMixer TSMixerx
MLPMultivariate iTransformer BiTCN TiDE DeepNPTS SOFTS SOFTSSharp
TimeMixer KAN RMoK TimeXer xLSTM XLinear
```

Direct shared subset:

```text
DLinear
NLinear
NHITS
NBEATS
NBEATSx
TiDE
TCN
GRU
LSTM
DeepAR
TFT
PatchTST
TimesNet
TSMixer
TimeMixer
iTransformer
VanillaTransformer
```

The shared worker dynamically imports the class, configures h/input/training/device settings, fits on a chronological validation boundary and predicts.

Known implementation details:

- TimesNet has an explicit full-precision safety path when reduced precision is requested.
- multiseries classes require coherent `n_series`/layout.
- upstream class existence alone is insufficient to claim wrapper support for all 37.

## 9. NeuralForecast official AutoModels

Broad official AutoModel inventory: 36.

```text
AutoRNN AutoLSTM AutoGRU AutoTCN AutoDeepAR AutoDilatedRNN AutoBiTCN
AutoxLSTM AutoMLP AutoNBEATS AutoNBEATSx AutoNHITS AutoDLinear AutoNLinear
AutoTiDE AutoDeepNPTS AutoKAN AutoTFT AutoVanillaTransformer AutoInformer
AutoAutoformer AutoFEDformer AutoPatchTST AutoiTransformer AutoTimeXer
AutoTimesNet AutoStemGNN AutoHINT AutoTSMixer AutoTSMixerx
AutoMLPMultivariate AutoSOFTS AutoSOFTSSharp AutoTimeMixer AutoRMoK AutoXLinear
```

The shared AutoModel path resolves:

```text
Optuna or Ray backend
search strategy
num samples/trials
CPU/GPU resources
parallel trials/workers
precision
seed
refit policy
n_series where required
```

`AutoHINT` has dedicated hierarchy/base-model/distribution-loss/coherence handling.

### Local extensions

| Extension | Current interpretation |
|---|---|
| AutoTimeLLM | fail-closed local extension |
| AutoSCINet | local extension |
| AutoSegRNN | explicitly inactive |
| AutoFreTS | explicitly inactive |

Local code presence does not make a model an official shared AutoModel.

## 10. AutoGluon TimeSeries

Shared `autogluon-timeseries` does not rely on an unconstrained root import. It calls an isolated environment/provider:

```text
environments/autogluon-timeseries/
scripts/run_autogluon_timeseries_provider.py
```

Protocol v2 is the current normal path; v1 is compatibility-only.

Existing merged evidence includes real AutoGluon TimeSeries 1.5.0 CPU/fallback certification and a real Naive fit/predict/save + persisted load/predict smoke. It does not establish a positive GPU certification for the same path.

Runtime inventory distinguishes source-declared, runtime-discovered, runtime-importable and runtime-certified states.

## 11. Darts

Shared `darts-ensemble` creates per-position `RegressionEnsembleModel` over:

```text
NaiveDrift
ExponentialSmoothing
```

then fits and predicts one step.

## 12. GluonTS

Shared `gluonts-deepar` constructs Torch `DeepAREstimator` with Student-T output.

Current shared path explicitly configures:

```text
accelerator=cpu
devices=1
```

Therefore GluonTS execution code exists, but shared CUDA execution must **not** be claimed from this path.

## 13. ReservoirPy

Shared `reservoir-esn` constructs `Reservoir >> Ridge` per position with deterministic seed offsets and one-step forecast output.

## 14. HierarchicalForecast

This is a reconciliation layer, not an independent predictor.

Core NumPy:

```text
bottom_up
top_down
ols
wls_struct
mint_shrink
```

Optional upstream methods:

```text
BottomUp
BottomUpSparse
TopDown
TopDownSparse
MiddleOut
MiddleOutSparse
MinTrace
MinTraceSparse
OptimalCombination
ERM
```

Some methods require strict-tree structure. Registration does not mean every method is valid for every grouped hierarchy.

## 15. sktime

No direct `PositionSeriesWorker` branch is treated as the normal shared route.

Separate implementation:

```text
src/loto/sktime_campaign/**
```

It contains provider/campaign contracts for rolling-origin evaluation and later scientific stages. Use that lane explicitly.

## 16. skforecast

The optional dependency and broad entry exist, but no current direct shared worker branch was found in the audited execution path. Do not describe it as automatically runnable through `loto experiment research` without separate adapter/provider evidence.

## 17. BasicTS

Outside the 174 broad surface:

```text
src/loto/basicts_campaign/**
scripts/run_basicts_provider.py
```

The isolated provider has identity/config/dataset/runtime-smoke operations and a version-pinned CPU-oriented lane. Existing contract covers Numbers3/Numbers4/Mini/Loto6/Loto7 dataset payloads. Provider existence is not a claim of full OOF completion.

## 18. Time-Series-Library

Dedicated provider/campaign:

```text
src/loto/time_series_library_campaign/**
```

Explicit model operations currently include:

```text
DLinear
TSMixer
LightTS
SegRNN
FreTS
SCINet
TimeFilter
TiDE
FiLM
```

Operations include upstream discovery, training-bundle materialization, fit-save, load-predict, prediction-file verification and round-trip checks.

## 19. Merlion

Separate isolated integration:

```text
src/loto/merlion_campaign/**
```

It represents runtime/provenance/certification work and is neither a normal shared worker branch nor part of the current 174 forecast inventory count.

## 20. Shared foundation provider registry

`models/providers/registry.py` maps:

| ID/family | Provider |
|---|---|
| `chronos`, `chronos-bolt-tiny`, `chronos-t5-small`, `chronos-2`, `chronos-2-small` | ChronosProvider |
| `timesfm`, `timesfm-2.5` | TimesFMProvider |
| `granite-ttm` | GraniteTTMProvider |
| `tirex` | TiRexProvider |
| `moirai` | MoiraiProvider |
| `sundial` | SundialProvider |
| `tabpfn-ts` | TabPFNTSProvider |

Unknown provider IDs resolve to a fail-closed `ProviderNotImplemented`, not fake success.

## 21. Broad TSFM inventory

Current 21 broad entries:

```text
chronos-2
chronos-bolt-tiny
chronos-t5-small
chronos-t5-base
timesfm-2.5-transformers
granite-ttm-r2
granite-flowstate-r1
granite-patchtst
granite-patchtsmixer
moirai-2.0-small
moirai-1.0-base
tirex-2
toto-open-base
toto-2.0-4m
moment-1-small
moment-1-large
lag-llama
kronos-base
sundial-base
tabpfn-ts
t0-alpha
```

Broad declarations intentionally do not invent revisions. Formal execution binds a reviewed revision manifest.

## 22. TSFM runtime evidence

Current repository aggregate file:

```text
audit/tsfm-runtime/runtime-status.json
```

records:

```text
total_models=21
runtime_certified_models=19
```

Per-model records include model/revision/device/VRAM/PID/output evidence where captured.

Two known broad entries were not counted runtime-certified in this aggregate. Gated/licensing/artifact reasons must be read from the exact per-model record/evidence rather than inferred from the count.

Do not translate 19 runtime-certified identities into 19 OOF winners.

## 23. Verified TSFM revisions

```text
configs/tsfm/verified-revisions.json
```

is separate from raw broad-catalog `revision_status`. A catalog entry can show UNPINNED while a reviewed external manifest exists. Conversely a pin does not prove runtime load success.

## 24. Probabilistic platform

Separate 72-model catalog supports families such as:

```text
conjugate
dynamic_conjugate
empirical_bayes
bayesian_regression
hierarchical
state_space
changepoint
regime_switching
fixed_subset
copula
gaussian_process
tree_bayesian
mixture
nonparametric
calibration
decision
ensemble
deep_probabilistic
```

Optional backend mapping includes builtin, PyMC, PyMC-BART, NumPyro/JAX, Pyro/Torch, CmdStanPy, BlackJAX/JAX and TensorFlow Probability.

Examples of concrete native models in the catalog layer include:

```text
pp-conditional-bernoulli-fixed-k
pp-multinomial-dglm
pp-gaussian-copula-categorical
pp-bocpd-dirichlet-categorical
```

Use `loto3 probabilistic compatibility` before execution to validate model/game/backend support.

## 25. Unified campaign after #252

The campaign remains the six-game broad comparison adapter, but geometry-general scoring is now explicit:

- select hits preserve set semantics;
- digit hits preserve exact positions and repeated digits;
- required position error metrics use geometry width.

This closes the prior risk of treating Numbers3/4 as unordered sets.

## 26. Downstream theory/promotion after #253

New promotion evidence can use theory-aware v2 semantics. This is downstream governance, not a new model runtime route.

V2 requires sealed game identity and derives the actual Hit@±1 rule target from an IID-null-relative or absolute policy. Automatic promotion/retraining/registry write remain disabled.

## 27. Power planning after #254

`evaluation.power_analysis` adds pre-target planning utilities. It does not alter model inventory or routing status.

Use it to estimate whether a planned paired evaluation has enough draws to detect a declared effect size under the stated normal-approximation assumptions.

## 28. Capability labels

Use exactly:

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

Never infer later stages from earlier stages.

## 29. Current scientific boundary

This document audits code/runtime capability. It does not execute a new formal real-data campaign.

Current open workstreams identified in the live repository audit:

- #239 Timer Base 84M leakage-safe OOF;
- #118 Timer-S1 immutable runtime/certification PR-B.

Holdout/Prospective/promotion remain separate authorized stages.
