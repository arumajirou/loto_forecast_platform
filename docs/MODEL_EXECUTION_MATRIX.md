# Model and library execution matrix

> **Audit basis:** code and executable evidence on `main@0f7585bca90fe9c1578909018a2dc24fcfdc12cb`  
> **Audited:** 2026-08-10 16:47 JST  
> **Purpose:** describe what the repository can actually route, load, execute, or certify. This is not a restatement of the generated 174-entry inventory.

## 1. Why this document exists

The repository has several different model surfaces. Treating them as one list produces incorrect claims.

1. `src/loto/models/catalog_full.py` is the **broad inventory** used by `loto3 catalog`. It currently produces 174 registered entries.
2. `src/loto/models/catalog.py` is the **shared execution catalog** used by `loto models` and the main `loto experiment research` orchestration path.
3. `src/loto/models/workers.py` and `src/loto/models/factory.py` contain the **shared executable dispatch**.
4. `src/loto/models/providers/**` contains the **shared foundation-model provider registry**.
5. `src/loto/*_campaign/**`, `src/loto/adapters/**`, `scripts/run_*_provider.py`, and `environments/**` contain **isolated/provider-specific execution lanes** that may exist even when the model is not in the shared execution catalog.
6. `audit/**` contains point-in-time execution evidence. A successful runtime audit is stronger than registration, but it still does not prove lottery forecast accuracy or formal OOF superiority.

Therefore:

```text
registered != shared-routable != provider-implemented != runtime-certified != OOF-evaluated != promoted
```

## 2. Which CLI reads which catalog

| command/path | actual source | meaning |
|---|---|---|
| `uv run loto3 catalog --counts` | `loto.cli_v3` -> `catalog_full.build_catalog()` | broad 174-entry inventory |
| `uv run loto3 catalog --unpinned` | `catalog_full` revision metadata | inventory entries whose catalog revision field is not fixed; this is not the same as runtime audit status |
| `uv run loto models list` | `loto.cli` -> `catalog.list_model_specs()` | shared execution catalog |
| `uv run loto models show <id>` | `catalog.get_model_spec()` | one shared execution spec |
| `uv run loto experiment research --config ...` | `orchestration/research.py` -> `catalog.py` -> `RuntimeModel` / `PositionSeriesWorker` | actual shared multi-model research path |
| `uv run loto3 research ...` | `orchestration/research_v3.py` | separate v3 scientific loop; built-in mandatory predictors plus caller-injected predictors, not automatic execution of all catalog entries |

The two research commands are not interchangeable.

## 3. Shared research execution path

`src/loto/orchestration/research.py` performs chronological outer folds and resolves every configured model through `get_model_spec()`.

Dispatch is task-based:

```text
candidate
  -> RuntimeModel.fit_candidate()/predict_candidate()

position_series or foundation
  -> PositionSeriesWorker.forecast()

other task
  -> WorkerGateway job document, then explicit provider/plugin is required
```

The shared research path currently canonicalizes Loto7 data and its prediction helpers use the seven-position/37-candidate contract. Other game-specific providers may support more games, but that does not make this particular orchestration path multi-game automatically.

## 4. Direct candidate estimators

These are constructed in-process by `src/loto/models/factory.py` when their shared execution specs are selected.

| model/library | shared spec | executable code path | dependency |
|---|---|---|---|
| Uniform | `uniform` | `UniformCandidateAdapter` | core |
| Frequency | `frequency` | `FrequencyCandidateAdapter` | core |
| LogisticRegression | `logistic` | scikit-learn `LogisticRegression` | core |
| RandomForestClassifier | `random-forest` | scikit-learn | core |
| ExtraTreesClassifier | `extra-trees` | scikit-learn | core |
| HistGradientBoostingClassifier | `hist-gradient-boosting` | scikit-learn | core |
| LightGBM classifier | `lightgbm-classifier` | dynamic `lightgbm.LGBMClassifier` | `full` |
| XGBoost classifier | `xgboost-classifier` | dynamic `xgboost.XGBClassifier` | `full` |
| CatBoost classifier | `catboost-classifier` | dynamic `catboost.CatBoostClassifier` | `full` |

`RuntimeModel` excludes target/identity columns from numeric feature selection, fits the estimator, and normalizes `predict_proba`, `decision_function`, or `predict` output to candidate probabilities.

## 5. StatsForecast

### Broad inventory

`catalog_full.py` registers 41 StatsForecast estimators.

### Shared execution catalog

The shared `catalog.py` currently wires these concrete IDs:

- `stats-naive` -> `Naive`
- `stats-historic-average` -> `HistoricAverage`
- `stats-autoarima` -> `AutoARIMA`
- `stats-autoets` -> `AutoETS`
- `stats-autotheta` -> `AutoTheta`
- `stats-autoces` -> `AutoCES`
- `stats-croston` -> `CrostonClassic` as `candidate_series`
- `stats-tsb` -> `TSB` as `candidate_series`

`PositionSeriesWorker._statsforecast()` dynamically imports `statsforecast.models.<class>`, fits `StatsForecast`, and predicts horizon 1. `CrostonClassic` and `TSB` use a separate 37 binary candidate-series representation.

**Important:** 41 registered StatsForecast entries do not mean 41 IDs are currently selectable through `loto experiment research`; the shared execution catalog is the selection boundary for that command.

## 6. MLForecast

### Broad inventory

`catalog_full.py` records 8 `mlforecast_auto` entries.

### Shared execution path

`catalog.py` currently wires two direct `mlforecast` specs:

- `mlforecast-ridge`
- `mlforecast-lightgbm`

`PositionSeriesWorker._mlforecast()` builds lag features through `MLForecast`, using scikit-learn Ridge or LightGBM and horizon 1.

The eight broad AutoMLForecast registrations and the two shared execution IDs are different surfaces and must not be reported as eight automatically runnable shared-research models.

## 7. NeuralForecast fixed models

The broad inventory contains 37 fixed NeuralForecast models. The shared execution catalog currently contains a narrower directly-routable set:

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

`PositionSeriesWorker._neuralforecast()` dynamically imports the class from `neuralforecast.models`, supplies horizon/input/training defaults, selects CPU/GPU from the requested runtime, fits on a bounded validation window, and calls `NeuralForecast.predict()`.

Known code-level details:

- `TSMixer`, `TimeMixer`, and `iTransformer` receive `n_series=7` in this worker.
- `TimesNet` is explicitly forced to `32-true` when reduced precision was requested.
- the shared worker is a Loto7-style position-series path; model availability in NeuralForecast itself is not enough to prove this wrapper works for every class in the 37-entry broad inventory.

## 8. NeuralForecast AutoModels

The shared execution catalog contains the official AutoModel family and marks backend/search as runtime-resolved. `PositionSeriesWorker._neuralforecast_auto()` builds an `AutoModelRequest`, resolves Optuna/Ray/search policy, constructs the AutoModel, fits a chronological validation window, and predicts.

Runtime controls include:

```text
backend
num_samples
cpus
gpus
parallel_trials
refit_with_val
search_strategy
early_stop_patience_steps
seed
precision
n_series
```

`AutoHINT` is special-cased: it requires exactly seven coherent position series, creates an explicit total + seven-position hierarchy, uses a DLinear base model with a Normal `DistributionLoss`, and measures coherence error.

### Local extensions outside the shared official AutoModel list

The repository also contains local NeuralForecast extension code:

| extension | code exists | shared official AutoModel catalog state |
|---|---|---|
| AutoTimeLLM | `src/loto/neuralforecast/auto_timellm/**` | separate fail-closed local extension; do not equate with official shared registration |
| AutoSCINet | `src/loto/neuralforecast/auto_scinet/**` | local SCINet/AutoSCINet extension; separate from official shared catalog |
| AutoSegRNN | `src/loto/neuralforecast/auto_segrnn/**` | module explicitly identifies itself as **Inactive** |
| AutoFreTS | `src/loto/neuralforecast/auto_frets/**` | module explicitly identifies itself as **Inactive** |

File presence proves implementation work exists; it does not prove automatic shared-research selection or runtime certification.

## 9. AutoGluon TimeSeries

AutoGluon is not executed by importing it into the root Python environment. The shared worker calls an isolated subprocess:

```text
environments/autogluon-timeseries/
scripts/run_autogluon_timeseries_provider.py
```

`PositionSeriesWorker` requires the isolated `uv.lock`, invokes:

```text
uv run --project environments/autogluon-timeseries --locked python scripts/run_autogluon_timeseries_provider.py ...
```

and validates protocol-v2 request/response evidence. Schema v1 exists only as an explicit compatibility path.

Merged integration evidence for PR #237 records a real AutoGluon TimeSeries 1.5.0 CPU/fallback certification and a real shared-worker Naive fit/predict/save + persisted load/predict smoke. Positive GPU certification was not claimed by that integration.

The AutoGluon runtime catalog separately tracks:

```text
source_declared
runtime_discovered
runtime_importable
runtime_certified
```

so source discovery is intentionally not treated as runtime success.

## 10. Darts, GluonTS, ReservoirPy

These three framework entries have concrete shared worker branches.

### Darts

`_darts()` creates per-position `RegressionEnsembleModel` instances over `NaiveDrift()` and `ExponentialSmoothing()`, fits them, and predicts one step.

### GluonTS

`_gluonts()` constructs a Torch `DeepAREstimator` with Student-T output and predicts from `ListDataset` series.

Known limitation in current code: the trainer is explicitly hard-coded to:

```text
accelerator=cpu
devices=1
```

The source itself contains an audit comment that this has not yet been reconciled with `--device cuda/auto`. Therefore GluonTS shared-worker execution exists, but CUDA requests must not be documented as honored by this path.

### ReservoirPy

`_reservoir_esn()` constructs `Reservoir >> Ridge` per position with deterministic seed offsets and returns one-step position forecasts.

## 11. HierarchicalForecast

HierarchicalForecast is a reconciliation layer, not a normal `PositionSeriesWorker` model.

`src/loto/reconciliation/hierarchy.py` provides:

### Core NumPy reconciliation

```text
bottom_up
top_down
ols
wls_struct
mint_shrink
```

### Upstream HierarchicalForecast reconciliation

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

`reconcile_with_hierarchicalforecast()` imports the real optional package, constructs the requested method, executes `fit_predict`, checks finite/shape/coherence results, and returns explicit statuses for unavailable dependencies, unsupported hierarchy, missing in-sample data, configuration errors, and execution failures.

The repository's number hierarchy is grouped by total/parity/decade/number. Some upstream methods require a strict tree, so registration of all ten methods does not guarantee every method is valid for every hierarchy.

## 12. sktime and skforecast

The broad inventory and `frameworks` extra declare sktime and skforecast, but `PositionSeriesWorker.forecast()` has no direct `sktime` or `skforecast` dispatch branch.

### sktime

There is nevertheless a separate isolated sktime implementation under:

```text
src/loto/sktime_campaign/**
```

It exposes discovery/runtime/evaluation protocol types, rolling-origin evaluation, validation benchmarks, Holdout scoring and Prospective contracts. This is a provider/campaign lane, not the shared `PositionSeriesWorker` lane.

### skforecast

`skforecast` is present in the optional `frameworks` dependency set and broad catalog, but no direct shared worker branch was found in the audited `workers.py`. Do not describe it as automatically runnable through `loto experiment research` without a separate provider path/evidence.

## 13. BasicTS

BasicTS is implemented outside the 174-entry shared inventory surface.

Relevant code:

```text
src/loto/basicts_campaign/**
scripts/run_basicts_provider.py
```

The provider supports version-isolated request/response contracts. Current v1 operations include:

```text
identity
validate_config
compile_dataset
construct_forward_save_load_smoke
```

The contract pins BasicTS `1.1.0` and upstream revision `c2bb6e31e591167e84459775a21a62e70a5893ce`, defines CPU-only execution for that lane, and supports Numbers3/Numbers4/MiniLoto/Loto6/Loto7 dataset payloads.

This proves a real isolated BasicTS provider surface exists. It does not mean BasicTS models are counted in the 174-entry `catalog_full` or automatically selected by the shared research loop.

## 14. Time-Series-Library

Time-Series-Library also has a dedicated provider/campaign surface outside the 174-entry catalog:

```text
src/loto/time_series_library_campaign/**
```

`execute_request()` currently has explicit fit-save and load-predict operations for:

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

It also supports upstream model discovery, training-bundle materialization, validation, prediction-file verification, and round-trip verification.

These are concrete provider operations, not merely names in documentation. They remain separate from the normal `PositionSeriesWorker` dispatch and should be invoked through their campaign/provider contract.

## 15. Merlion

The repository has a separate Merlion integration under:

```text
src/loto/merlion_campaign/**
```

The package describes itself as an isolated runtime, provenance and certification contract. It is not part of the current 174-entry `catalog_full` count and is not a direct `PositionSeriesWorker` branch.

## 16. Foundation-model shared provider registry

The shared foundation dispatch is real code:

```text
PositionSeriesWorker._foundation()
  -> get_foundation_provider(spec)
  -> provider.load()
  -> provider.predict(history)
  -> provider.inspect_properties()
  -> provider.close()
```

`src/loto/models/providers/registry.py` currently registers shared provider classes for:

| shared ID/family | provider implementation |
|---|---|
| `chronos`, `chronos-bolt-tiny`, `chronos-t5-small`, `chronos-2`, `chronos-2-small` | `ChronosProvider` |
| `sundial` | `SundialProvider` |
| `timesfm`, `timesfm-2.5` | `TimesFMProvider` |
| `granite-ttm` | `GraniteTTMProvider` |
| `tirex` | `TiRexProvider` |
| `moirai` | `MoiraiProvider` |
| `tabpfn-ts` | `TabPFNTSProvider` |

Unknown IDs fall back to `ProviderNotImplemented`, which raises `PROVIDER_NOT_IMPLEMENTED` rather than silently pretending success.

Chronos is additionally fail-closed around local snapshots: the provider checks required local weight/config files and uses dedicated provider runners for pinned Chronos Bolt Tiny, Chronos T5 Small and Chronos 2 paths.

## 17. TSFM runtime evidence: 21 audited, 19 certified, 2 blocked

The strongest current codebase evidence for the broad 21-model TSFM inventory is:

```text
audit/tsfm-runtime/runtime-status.json
configs/tsfm/verified-revisions.json
```

The runtime-status counters on current `main` are:

```text
total_models=21
certified_models=19
blocked_models=2
pending_models=0
judged_models=21
judged_progress_percent=100.0
```

The two blocked models are:

| model | current evidence status | reason |
|---|---|---|
| `moirai-1.0-base` | BLOCKED | exact pinned snapshot lacks required config/model weights; personal non-commercial license scope |
| `t0-alpha` | BLOCKED | gated access required |

The other 19 entries have `runtime_status=CERTIFIED` in the aggregate audit. This includes Chronos variants, IBM Granite variants, Kronos, Lag-Llama, Moirai 2.0 small, MOMENT variants, Sundial, TabPFN-TS, TimesFM 2.5 Transformers, TiRex 2 and Toto variants.

### Important certification-scope caveat

`CERTIFIED` here means the recorded runtime certification contract passed for that model. It does **not** uniformly mean “lottery forecast model ready for OOF”. Per-model evidence can be narrower:

- Kronos certification uses its native financial OHLCV/K-line contract and explicitly records `lottery_domain_compatibility_certified=false`.
- Moirai 2.0 Small records full inference but also `lottery_domain_compatibility_certified=false`, and its license is personal/non-commercial only.
- MOMENT runtime evidence can be execution-only where a pretrained forecasting head is not available without fine-tuning.
- runtime certification never proves Hit@±1 improvement or baseline superiority.

Always inspect the per-model `audit/tsfm-runtime/<model>/runtime-certification.json` before promotion to an experiment lane.

### Internal aggregate inconsistency found by this audit

The same `runtime-status.json` stores `certified_models=19` and `total_models=21` but also stores:

```text
formal_certification_rate_percent=42.9
```

19 / 21 is approximately 90.5%, so that percentage field is stale or based on an older certification definition. The counters and per-model records are retained as evidence; this document does **not** rewrite the historical audit artifact. Do not quote 42.9% as the current 19/21 arithmetic certification rate without explaining the discrepancy.

## 18. Runtime pins versus `loto3 catalog --unpinned`

`configs/tsfm/verified-revisions.json` contains explicit immutable revisions for all 21 TSFM audit identities.

This can coexist with `loto3 catalog --unpinned` reporting TSFM entries as `UNPINNED` because the broad catalog's base declarations and the separate verified-revision manifest are different layers. A formal run must bind the verified revision/artifact identity; the raw broad-catalog field alone is insufficient.

Do not interpret:

```text
catalog revision_status=UNPINNED
```

as “no pinned runtime evidence exists anywhere in the repository”. Conversely, do not interpret a verified-revision manifest as proof of load/inference success; runtime evidence is still required.

## 19. What `pyproject.toml` actually installs

| lane | actual dependency intent |
|---|---|
| core | NumPy, pandas, Pydantic, scikit-learn, SciPy, NeuralForecast 3.2.0, Torch 2.9.1, Transformers 4.57.6, HF Hub, PyArrow, etc. |
| `auto-campaign` | Optuna + StatsForecast + psutil |
| `full` | LightGBM/XGBoost/CatBoost/StatsForecast/MLForecast/HierarchicalForecast/NeuralForecast/Optuna/Ray/telemetry/etc. |
| `frameworks` | Darts, GluonTS, Lightning, sktime, skforecast, ReservoirPy |
| `tsfm` | Transformers, Accelerate, Chronos forecasting |

Several heavy/provider-specific integrations use their own `environments/**/pyproject.toml` and lockfiles. Root extras are not evidence that every isolated provider can run under one root environment.

## 20. Capability levels used in this repository

Use these labels when updating documentation:

| level | evidence required |
|---|---|
| `REGISTERED` | model/library appears in an inventory/catalog |
| `DEPENDENCY_DECLARED` | root extra or isolated environment declares package |
| `IMPLEMENTED` | adapter/provider/worker code exists |
| `SHARED_ROUTABLE` | normal shared research dispatch can select it |
| `PROVIDER_ROUTABLE` | isolated provider/campaign entrypoint exists |
| `RUNTIME_CERTIFIED` | real load/inference/runtime evidence exists for an exact identity |
| `LOTTERY_COMPATIBLE` | runtime path is verified on the repository's lottery geometry/data contract |
| `OOF_EVALUATED` | leakage-safe chronological OOF has actually run |
| `HOLDOUT_EVALUATED` | authorized Holdout gate has run |
| `PROSPECTIVE_EVALUATED` | prediction was sealed before future actual and then scored |
| `PROMOTION_ELIGIBLE` | scientific/runtime/license/governance gates all pass |

Never collapse these levels to a single `available=true` claim.

## 21. Current scientific boundary

This capability audit does not execute new model inference or scientific evaluation. In particular it does not change the Timer Base 84M campaign boundary tracked by Issue #239 / Linear TAJ-12:

```text
formal_timer_oof_run=false
holdout_opened=false
prospective_opened=false
accuracy_claim=false
champion_claim=false
promotion=false
```

The repository contains substantially more executable model/provider code than the 174-entry inventory alone communicates, but scientific use still requires an explicit execution identity, leakage-safe protocol and evidence for the exact path being promoted.