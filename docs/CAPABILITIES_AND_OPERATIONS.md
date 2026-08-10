# Capabilities and Operations Reference

```text
status_class: LIVE_REFERENCE
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
```

この文書は、Loto Forecast Platformの**機能をlibrary/model/実行lane/科学gate単位で引くための実務リファレンス**です。

## 1. Capability status

| 状態 | 意味 |
|---|---|
| `REGISTERED` | broad/shared catalogにentryがある |
| `DEPENDENCY_DECLARED` | root extraまたはisolated environmentがdependencyを宣言 |
| `IMPLEMENTED` | adapter/provider/worker/campaign codeがある |
| `SHARED_ROUTABLE` | normal shared execution pathから選択可能 |
| `PROVIDER_ROUTABLE` | isolated provider/campaign entrypointがある |
| `RUNTIME_CERTIFIED` | exact identityでload/inference evidenceがある |
| `LOTTERY_COMPATIBLE` | lottery geometry/data contract上でruntime pathを検証 |
| `OOF_EVALUATED` | chronological leakage-safe OOFを実行済み |
| `HOLDOUT_EVALUATED` | authorization後のHoldoutを評価済み |
| `PROSPECTIVE_EVALUATED` | sealed future predictionをactual到着後に評価済み |
| `PROMOTION_ELIGIBLE` | policy gateがpassしhuman approval候補になった |

`available=true`やimport成功だけで後段へ昇格しません。

## 2. Command selection

| Goal | Recommended command | Notes |
|---|---|---|
| game geometry | `uv run loto3 games` | 6 canonical games |
| IID-null theory | `uv run loto3 theory --game GAME --tau 1` | theory reference only |
| broad model inventory | `uv run loto3 catalog --counts` | 174 entries |
| shared model inventory | `uv run loto models list` | executable `ModelSpec` surface |
| full model×game planning | `uv run loto3 campaign --output unused --plan-only` | no inference |
| unified development comparison | `uv run loto3 campaign ...` | 6-game geometry, fail-visible matrix |
| NeuralForecast AutoModel HPO | `uv run loto neuralforecast automodel-run ...` | Optuna/Ray |
| probabilistic catalog | `uv run loto3 probabilistic catalog-list` | 72 models |
| probabilistic backend probe | `uv run loto3 probabilistic backends` | PyMC/NumPyro/Pyro/etc. |
| hierarchy | `uv run loto3 hierarchy ...` | reconciliation |
| TSFM pins | `uv run loto3 revisions ...` | explicit immutable revision manifest |
| data acquisition | `uv run loto data acquire ...` | one or many games |
| local API | `uv run loto3 probabilistic api-*` | authenticated execution API |
| run control | `uv run loto3 probabilistic run-*` | allowed profiles only |

## 3. Game compatibility contract

| game | family | positions | values | special semantics |
|---|---|---:|---|---|
| mini | select | 5 | 1..31 | ascending, distinct |
| loto6 | select | 6 | 1..43 | ascending, distinct |
| loto7 | select | 7 | 1..37 | ascending, distinct |
| bingo5 | select | 8 | 1..40 | ascending, distinct |
| numbers3 | digits | 3 | 0..9 | ordered, repeated digits allowed |
| numbers4 | digits | 4 | 0..9 | ordered, repeated digits allowed |

Model/provider compatibility must be evaluated against this geometry. A Loto7-specific worker or fixed seven-series assumption is not automatically multi-game.

## 4. Library execution matrix

| Library / family | Broad inventory | Shared route | Isolated/provider route | Typical use |
|---|---:|---|---|---|
| builtin | 4 | yes | n/a | theory/frequency controls |
| scikit-learn | 7 | yes | n/a | candidate + position ML |
| LightGBM | 2 | yes | n/a | candidate/position boosting |
| XGBoost | 1 | yes | n/a | candidate boosting |
| CatBoost | 1 | yes | n/a | candidate boosting |
| StatsForecast | 41 | 8 explicit shared IDs | campaign-dependent | statistical forecasting |
| MLForecast Auto inventory | 8 | 2 direct MLForecast IDs | separate AutoML semantics | lag ML |
| NeuralForecast fixed | 37 | 17 direct shared classes | local extensions also exist | deep forecasting |
| NeuralForecast Auto | 36 | official AutoModel family wired | local extensions separate | Optuna/Ray HPO |
| AutoGluon TimeSeries | 1 broad entry | subprocess bridge | `environments/autogluon-timeseries` | AutoML/ensemble |
| Darts | 1 | `darts-ensemble` | optional | ensemble framework |
| GluonTS | 1 | `gluonts-deepar` | optional | probabilistic DeepAR |
| ReservoirPy | 1 | `reservoir-esn` | optional | ESN |
| HierarchicalForecast | 10 | reconciliation, not standalone forecasters | optional package | coherent forecasts |
| sktime | 1 | no direct shared worker branch | `sktime_campaign` | rolling-origin campaign |
| skforecast | 1 | no direct shared worker branch | no audited equivalent shared adapter | dependency/inventory only until routed |
| BasicTS | outside 174 | no | `basicts_campaign` | isolated benchmark/provider |
| Time-Series-Library | outside 174 | no | `time_series_library_campaign` | architecture benchmark/provider |
| Merlion | outside 174 | no | `merlion_campaign` | isolated runtime/certification |
| TSFM | 21 | selected provider IDs | several provider-specific lanes | zero-shot/foundation models |
| probabilistic programming | separate 72-model catalog | `loto3 probabilistic` | backend-dependent | Bayesian/state-space/copula/etc. |

## 5. Direct candidate models

Shared candidate IDs:

```text
uniform
frequency
logistic
random-forest
extra-trees
hist-gradient-boosting
lightgbm-classifier
xgboost-classifier
catboost-classifier
```

These operate on candidate feature matrices and normalize estimator outputs into the candidate scoring contract.

Recommended use:

1. inspect with `loto models show`;
2. run a bounded synthetic campaign first;
3. confirm feature chronology;
4. compare against mandatory baselines;
5. preserve all seeds and sealed predictions.

## 6. Position-series models

Shared examples:

```text
ridge-position
elasticnet-position
lightgbm-position
mlforecast-ridge
mlforecast-lightgbm
stats-naive
stats-historic-average
stats-autoarima
stats-autoets
stats-autotheta
stats-autoces
```

Position/foundation models must return finite output with width equal to `geometry.positions`.

## 7. NeuralForecast fixed

Broad fixed class inventory:

```text
RNN GRU LSTM TCN DeepAR DilatedRNN MLP NHITS NBEATS NBEATSx
DLinear NLinear TFT VanillaTransformer Informer Autoformer PatchTST
FEDformer StemGNN HINT TimesNet TimeLLM TSMixer TSMixerx
MLPMultivariate iTransformer BiTCN TiDE DeepNPTS SOFTS SOFTSSharp
TimeMixer KAN RMoK TimeXer xLSTM XLinear
```

Direct shared class subset:

```text
DLinear NLinear NHITS NBEATS NBEATSx TiDE TCN GRU LSTM DeepAR
TFT PatchTST TimesNet TSMixer TimeMixer iTransformer VanillaTransformer
```

The subset is a routing fact, not a judgment that the remaining upstream models are unusable. They require explicit route/provider evidence before being reported as shared-executable.

## 8. NeuralForecast AutoModels

Official AutoModel inventory:

```text
AutoRNN AutoLSTM AutoGRU AutoTCN AutoDeepAR AutoDilatedRNN AutoBiTCN
AutoxLSTM AutoMLP AutoNBEATS AutoNBEATSx AutoNHITS AutoDLinear AutoNLinear
AutoTiDE AutoDeepNPTS AutoKAN AutoTFT AutoVanillaTransformer AutoInformer
AutoAutoformer AutoFEDformer AutoPatchTST AutoiTransformer AutoTimeXer
AutoTimesNet AutoStemGNN AutoHINT AutoTSMixer AutoTSMixerx
AutoMLPMultivariate AutoSOFTS AutoSOFTSSharp AutoTimeMixer AutoRMoK AutoXLinear
```

Runtime search controls include backend, search strategy, trials, CPUs, GPUs, trial parallelism, precision, seed and refit policy.

### Local extensions

- AutoTimeLLM — fail-closed local extension.
- AutoSCINet — local extension.
- AutoSegRNN — currently marked inactive.
- AutoFreTS — currently marked inactive.

Do not report an inactive/local extension as an official upstream AutoModel.

## 9. StatsForecast

Broad inventory 41 includes ARIMA/ETS/Theta/decomposition/intermittent/volatility/control models. Shared IDs are deliberately smaller:

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

Croston/TSB use candidate-series semantics rather than the ordinary position-series route.

## 10. MLForecast

Broad AutoML inventory:

```text
AutoLightGBM AutoXGBoost AutoCatboost AutoLinearRegression
AutoRidge AutoLasso AutoElasticNet AutoRandomForest
```

Current direct shared paths:

```text
mlforecast-ridge
mlforecast-lightgbm
```

The broad AutoML inventory is useful for coverage planning/research expansion; it is not eight automatically routed shared workers.

## 11. Foundation-model providers

Shared provider registry:

| ID | Provider | Identity notes |
|---|---|---|
| chronos-bolt-tiny | ChronosProvider | pinned shared spec |
| chronos-t5-small | ChronosProvider | pinned shared spec |
| chronos-2 | ChronosProvider | `amazon/chronos-2`, pinned shared revision |
| chronos-2-small | ChronosProvider | AutoGluon Chronos2 small identity |
| timesfm-2.5 | TimesFMProvider | TimesFM 2.5 path |
| granite-ttm | GraniteTTMProvider | Transformers TTM path |
| tirex | TiRexProvider | `NX-AI/TiRex-2`, pinned shared revision |
| moirai | MoiraiProvider | `Salesforce/moirai-2.0-R-small`, pinned shared revision |
| sundial | SundialProvider | remote-code-sensitive path |
| tabpfn-ts | TabPFNTSProvider | candidate/foundation-tabular path |

Unknown providers fail with `PROVIDER_NOT_IMPLEMENTED`.

### Broad TSFM inventory

21-entry broad inventory additionally tracks Chronos T5 Base, Granite FlowState/Patch models, Moirai 1.0, Toto, MOMENT, Lag-Llama, Kronos, T0 and others. A broad entry may require a dedicated provider not used by the normal shared worker.

### Runtime evidence

`audit/tsfm-runtime/runtime-status.json` currently records 21 models and 19 runtime-certified identities. Treat the file as point-in-time runtime evidence only. It does not establish real-data OOF quality or six-game success.

## 12. AutoGluon

Execution isolation:

```text
environments/autogluon-timeseries/
scripts/run_autogluon_timeseries_provider.py
```

The root worker communicates through a request/response protocol rather than relying on an unconstrained root import. Runtime discovery/certification is separate from source-declared model inventory.

Promotion eligibility v2 is theory-aware and game-bound, but remains manual-only.

## 13. Time-Series-Library

Dedicated campaign supports concrete operations for:

```text
DLinear TSMixer LightTS SegRNN FreTS SCINet TimeFilter TiDE FiLM
```

Use the campaign/provider contract for training bundle creation, fit-save, load-predict and verification. Do not route these by pretending they are normal `catalog.py` ModelSpecs.

## 14. BasicTS

Dedicated provider supports isolated identity/config/dataset/runtime smoke operations. Current contract is CPU-oriented and version-pinned. It is a provider certification surface, not a direct shared campaign model family.

## 15. Darts / GluonTS / ReservoirPy

- Darts: `RegressionEnsembleModel` over `NaiveDrift` + `ExponentialSmoothing` per position.
- GluonTS: Torch `DeepAREstimator` with Student-T output; current shared path is CPU-pinned and must not be presented as CUDA-certified.
- ReservoirPy: `Reservoir >> Ridge` ESN per position.

## 16. Reconciliation

Core reconciliation:

```text
bottom_up top_down ols wls_struct mint_shrink
```

Optional upstream HierarchicalForecast:

```text
BottomUp BottomUpSparse TopDown TopDownSparse MiddleOut MiddleOutSparse
MinTrace MinTraceSparse OptimalCombination ERM
```

Reconciliation methods transform base forecasts; they are not independent forecasters. Unified coverage represents them as non-standalone where appropriate.

## 17. Probabilistic model platform

Separate 72-model catalog supports multiple inference families and optional packages.

Backend probe:

```bash
uv run loto3 probabilistic backends
```

Compatibility before run:

```bash
uv run loto3 probabilistic compatibility \
  --model-id <model> \
  --game numbers3 \
  --backend builtin
```

Then validate → plan → smoke → run → status/diagnose/compare.

This surface also exposes authenticated local run-control API and VOICEVOX TTS integration.

## 18. Unified evaluation workflow

Recommended order:

```text
1. immutable data snapshot
2. geometry/data validation
3. campaign --plan-only
4. resource budget + seeds fixed
5. chronological development folds
6. mandatory baselines
7. model/provider execution
8. family-aware decoding/legalisation
9. prediction write/fsync/SHA-256 before actual read
10. scoring and seed aggregation
11. failure/status classification
12. scientific review
13. only then consider Holdout authorization
```

## 19. Metrics

Primary: Hit@±1.

Required companion metrics:

- per-position Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE.

Geometry-general metrics preserve digit positional semantics and select set-overlap semantics.

## 20. Decoder

Probability-bearing candidate route:

```text
row-normalized slot binary probability
-> digits: positional ±tau window utility
-> select: legality-constrained ±tau dynamic programming
-> legal prediction
```

Point-only routes remain point-only.

## 21. Theory guard

`TheoryAwareThreshold` supports:

- `absolute`;
- `excess_vs_iid_null`.

The exact IID-null reference is used to prevent accidental impossible/misleading targets. Absolute targets beyond the IID-null ceiling require an explicit alternative hypothesis. The ceiling is not described as a universal ceiling under every possible biased process.

## 22. Promotion policy

Promotion v2 requires sealed scoring `game_id` matching the policy game, fixes tau=1, resolves theory semantics to an absolute target and evaluates prospective windows/baselines/degradation.

Even when every rule passes:

```text
ELIGIBLE_FOR_HUMAN_APPROVAL
```

is the maximum automatic decision. Automatic promotion, retraining and registry writes are forbidden by the policy model.

## 23. MDE and power planning

`paired-score-normal-approximation-v1` provides:

- required paired draw count for a declared effect;
- MDE at a declared draw count;
- deterministic MDE curves;
- Bonferroni planning alpha for multiplicity.

`score_sd` must be fixed before the target evaluation window. These calculations are experiment-planning evidence, not realized significance tests.

## 24. Runtime certification checklist

A runtime claim should record where applicable:

```text
model ID / repo / revision
artifact hashes
runtime / Python / package lock
requested and effective device
input shape/context/horizon
load result
inference result
output shapes/finite checks
GPU PID / VRAM / utilization / fallback
save/reload result
cleanup/VRAM release
code/config/data/protocol hashes
```

A catalog count is never a substitute for this evidence.

## 25. Scientific acceptance checklist

Before claiming OOF superiority:

- same eligible folds;
- same game geometry;
- same metric implementation;
- all mandatory baselines;
- all approved seeds;
- no train/future leakage;
- prediction-before-actual seal;
- compatible protocol hashes;
- model/runtime identity fixed;
- failures retained.

Before Holdout: OOF evidence must be reviewed and Holdout explicitly authorized.

Before Prospective scoring: prediction must have been sealed before the future actual was available/read.

Before promotion: runtime, OOF, Holdout, multiple Prospective windows, baseline and governance rules must all pass, followed by human approval.

## 26. Known current limits

- Broad 174-entry planning does not imply 174 successful shared executions.
- `loto experiment research` contains older/Loto7-oriented assumptions; use `loto3 campaign` for canonical six-game comparison.
- Some framework/provider lanes are CPU-only or have device-specific limitations.
- Some broad TSFM entries are gated/blocked or require provider work.
- The complete real-data 174 × 6 outcome is not claimed by documentation alone.
- Open scientific/runtime work remains tracked in current `docs/STATUS.md` and GitHub issues.
