# Model Device Matrix (GPU_STRICT audit, Phase 2)

> **Historical audit snapshot**
>
> This report records the Phase 2 code-inspection state and is not the current
> runtime-certification source of truth. Several models classified here as
> unprobed, CPU-forced, or ineligible were subsequently certified on CUDA.
>
> For current empirical runtime status, use:
>
> - `audit/tsfm-runtime/runtime-status.json`
> - `audit/tsfm-runtime/*/runtime-certification.json`
> - `docs/tsfm-runtime-certification-progress.md`
>
> The machine-readable policy below may also predate later runtime
> certifications and must not override direct GPU execution evidence.


Machine-readable source of truth: `configs/model_device_policy.json`. This report is the human-readable companion covering the same 84-model classification, generated from direct reads of `workers.py`, `factory.py`, `providers/base.py`, `providers/moirai.py`, `catalog.py`, and a cross-provider grep of `run_formal_model_backtest.py` + every `run_*_provider.py` script.

## Summary counts

| device_class | count |
|---|---|
| GPU_REQUIRED | 53 |
| GPU_OPTIONAL | 10 |
| CPU_ONLY | 20 |
| GPU_BLOCKED_ENVIRONMENT | 0 |
| PROVIDER_BROKEN | 1 |
| **TOTAL** | **84** |

Note: `GPU_BLOCKED_ENVIRONMENT` is currently 0 by design -- no model is classified into this bucket without an empirical diagnostic proving an environment-level kernel/wheel mismatch (the standard this audit applies, per Moirai's precedent). Several `GPU_REQUIRED`/`GPU_OPTIONAL` models (timesfm-2.5, tirex, sundial, granite-ttm re-probe) are NOT yet probed and are marked `formal_eligibility: false` with an honest 'not yet probed' blocking reason rather than being guessed into GPU_BLOCKED_ENVIRONMENT or GPU_CERTIFIED.

## GPU_REQUIRED (53)

| model_id | framework | family | current resolved device | formal eligibility | blocking reason |
|---|---|---|---|---|---|
| `nf-dlinear` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-nlinear` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-nhits` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-nbeats` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-nbeatsx` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-tide` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-tcn` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-gru` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-lstm` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-deepar` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-tft` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-patchtst` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-timesnet` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-tsmixer` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-timemixer` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-itransformer` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-vanilla-transformer` | neuralforecast | deep | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU e... |
| `nf-auto-rnn` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-lstm` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-gru` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-tcn` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-deepar` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-dilatedrnn` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-bitcn` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-mlp` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-nbeats` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-nbeatsx` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-nhits` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-dlinear` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-nlinear` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-tide` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-deepnpts` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-kan` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-tft` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-vanilla-transformer` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-informer` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-autoformer` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-fedformer` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-patchtst` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-itransformer` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-timexer` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-timesnet` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-stemgnn` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-tsmixer` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-tsmixerx` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-mlp-multivariate` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-softs` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-timemixer` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-rmok` | neuralforecast | neuralforecast_auto | cuda (when --device cuda/auto and CUDA available) | ❌ | none identified in code; formal eligibility pending Phase 9 1-fold probe. |
| `nf-auto-hint` | neuralforecast | hierarchical | cpu (hardcoded) | ❌ | workers._autohint hardcodes base_model_config['accelerator']='cpu' and never reads self.device at all, unlike _neuralforecast/_neuralfore... |
| `timesfm-2.5` | timesfm | tsfm | unresolved -- not yet probed this session | ❌ | Dedicated environment (environments/timesfm) has not been probed this session -- GPU kernel compatibility on this RTX 5070 Ti (sm_120) is... |
| `moirai` | uni2ts | tsfm | cuda (verified) | ✅ | none (resolved) |
| `sundial` | transformers | tsfm | unresolved -- not yet probed this session | ❌ | Dedicated environment (environments/sundial) has not been probed this session; GPU kernel compatibility on sm_120 unconfirmed. |

## GPU_OPTIONAL (10)

| model_id | framework | family | current resolved device | formal eligibility | blocking reason |
|---|---|---|---|---|---|
| `lightgbm-classifier` | lightgbm | tree | cpu | ❌ | Pure code-wiring gap, not an environment limitation: factory.RuntimeModel constructs LGBMClassifier with no device parameter and never pa... |
| `lightgbm-position` | lightgbm | tree | cpu | ❌ | Pure code-wiring gap, not an environment limitation: workers._lag_regression constructs LGBMRegressor with no device parameter and never ... |
| `xgboost-classifier` | xgboost | tree | cpu | ❌ | Pure code-wiring gap, not an environment limitation: factory.RuntimeModel constructs XGBClassifier with no device parameter and never pas... |
| `catboost-classifier` | catboost | tree | cpu | ❌ | Pure code-wiring gap, not an environment limitation: factory.RuntimeModel constructs CatBoostClassifier with no device parameter and neve... |
| `mlforecast-lightgbm` | lightgbm | lag_ml | cpu | ❌ | Pure code-wiring gap, not an environment limitation: workers._mlforecast constructs LGBMRegressor with no device parameter and never pass... |
| `gluonts-deepar` | gluonts | deep_probabilistic | cpu (hardcoded) | ❌ | workers._gluonts hardcodes trainer_kwargs['accelerator']='cpu', with the same pre-existing AUDIT comment (dated 2026-07-31, 'Phase 11') a... |
| `chronos-bolt-tiny` | chronos | tsfm | cuda (when --device cuda and CUDA available) | ❌ | Not yet probed with a real GPU-evidence-capturing run this session. |
| `chronos-2-small` | chronos | tsfm | cuda (when --device cuda and CUDA available) | ❌ | Same as chronos-bolt-tiny (not yet probed); additionally the missing capability tag means catalog-driven model selection may not even sur... |
| `granite-ttm` | transformers | tsfm | cpu (hardcoded at orchestrator level) | ❌ | scripts/run_formal_model_backtest.py lines 570-572 unconditionally force effective_device='cpu' with fallback_reason='granite_ttm_forced_... |
| `tirex` | tirex | tsfm | unresolved -- not yet probed this session | ❌ | Dedicated environment (environments/tirex) has not been probed this session. |

## PROVIDER_BROKEN (1)

| model_id | framework | family | current resolved device | formal eligibility | blocking reason |
|---|---|---|---|---|---|
| `tabpfn-ts` | tabpfn_time_series | foundation_tabular | n/a (fails before producing a prediction on either device) | ❌ | Fails on BOTH CUDA and CPU with "unsupported operand type(s) for +: 'int' and 'NoneType'" -- a provider/input-conversion defect that occu... |

## CPU_ONLY (20)

| model_id | framework | family | current resolved device | formal eligibility | blocking reason |
|---|---|---|---|---|---|
| `uniform` | builtin | theory | cpu | ✅ | none |
| `frequency` | builtin | frequency | cpu | ✅ | none |
| `logistic` | sklearn | linear | cpu | ✅ | none |
| `ridge-position` | sklearn | linear | cpu | ✅ | none |
| `elasticnet-position` | sklearn | linear | cpu | ✅ | none |
| `random-forest` | sklearn | tree | cpu | ✅ | none |
| `extra-trees` | sklearn | tree | cpu | ✅ | none |
| `hist-gradient-boosting` | sklearn | tree | cpu | ✅ | none |
| `mlforecast-ridge` | mlforecast | lag_ml | cpu | ✅ | none |
| `stats-naive` | statsforecast | statistical | cpu | ✅ | none |
| `stats-historic-average` | statsforecast | statistical | cpu | ✅ | none |
| `stats-autoarima` | statsforecast | statistical | cpu | ✅ | none |
| `stats-autoets` | statsforecast | statistical | cpu | ✅ | none |
| `stats-autotheta` | statsforecast | statistical | cpu | ✅ | none |
| `stats-autoces` | statsforecast | statistical | cpu | ✅ | none |
| `stats-croston` | statsforecast | intermittent | cpu | ✅ | none |
| `stats-tsb` | statsforecast | intermittent | cpu | ✅ | none |
| `autogluon-timeseries` | autogluon | automl | cpu | ✅ | Conflation of a fast-CPU smoke preset with formal GPU-capable execution (Phase 1 problem #3). |
| `darts-ensemble` | darts | framework | cpu | ✅ | none |
| `reservoir-esn` | reservoirpy | reservoir | cpu | ✅ | none |

## Full rationale (per model)

### `uniform`

- **device_class**: CPU_ONLY
- **framework**: builtin
- **model_family**: theory
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: UniformCandidateAdapter is a pure Python/pandas frequency-count adapter with no tensor computation of any kind; there is no GPU implementation to invoke.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `frequency`

- **device_class**: CPU_ONLY
- **framework**: builtin
- **model_family**: frequency
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: FrequencyCandidateAdapter is a pure Python/pandas frequency-count adapter with no tensor computation of any kind; there is no GPU implementation to invoke.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `logistic`

- **device_class**: CPU_ONLY
- **framework**: sklearn
- **model_family**: linear
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: scikit-learn's LogisticRegression (dispatched via factory.RuntimeModel) has no CUDA/GPU backend; scikit-learn only ships CPU (BLAS/OpenMP) implementations for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `ridge-position`

- **device_class**: CPU_ONLY
- **framework**: sklearn
- **model_family**: linear
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: scikit-learn's Ridge (dispatched via workers._lag_regression) has no CUDA/GPU backend; scikit-learn only ships CPU (BLAS/OpenMP) implementations for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `elasticnet-position`

- **device_class**: CPU_ONLY
- **framework**: sklearn
- **model_family**: linear
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: scikit-learn's ElasticNet (dispatched via workers._lag_regression) has no CUDA/GPU backend; scikit-learn only ships CPU (BLAS/OpenMP) implementations for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `random-forest`

- **device_class**: CPU_ONLY
- **framework**: sklearn
- **model_family**: tree
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: scikit-learn's RandomForestClassifier (dispatched via factory.RuntimeModel) has no CUDA/GPU backend; scikit-learn only ships CPU (BLAS/OpenMP) implementations for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `extra-trees`

- **device_class**: CPU_ONLY
- **framework**: sklearn
- **model_family**: tree
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: scikit-learn's ExtraTreesClassifier (dispatched via factory.RuntimeModel) has no CUDA/GPU backend; scikit-learn only ships CPU (BLAS/OpenMP) implementations for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `hist-gradient-boosting`

- **device_class**: CPU_ONLY
- **framework**: sklearn
- **model_family**: tree
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: scikit-learn's HistGradientBoostingClassifier (dispatched via factory.RuntimeModel) has no CUDA/GPU backend; scikit-learn only ships CPU (BLAS/OpenMP) implementations for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `mlforecast-ridge`

- **device_class**: CPU_ONLY
- **framework**: mlforecast
- **model_family**: lag_ml
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: mlforecast wraps sklearn Ridge for this entry; Ridge has no GPU backend.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `lightgbm-classifier`

- **device_class**: GPU_OPTIONAL
- **framework**: lightgbm
- **model_family**: tree
- **current_resolved_device**: cpu
- **gpu_support_rationale**: LGBMClassifier (lightgbm) has an official GPU training backend (enabled via device_type="gpu"); catalog.py tags this model 'gpu_optional'.
- **cpu_only_rationale**: n/a (library supports both CPU and GPU; CPU is the library default when no GPU kwarg is passed)
- **blocking_reason**: Pure code-wiring gap, not an environment limitation: factory.RuntimeModel constructs LGBMClassifier with no device parameter and never passes device_type="gpu" (or any GPU-enabling kwarg) regardless of the --device CLI setting. Confirmed by reading the full constructor body.
- **required_fix**: Add a device parameter to factory and pass device_type="gpu" conditioned on the resolved device being cuda; then empirically verify (Phase 8) that the installed lightgbm wheel actually has a GPU backend compiled in before trusting any GPU run.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `lightgbm-position`

- **device_class**: GPU_OPTIONAL
- **framework**: lightgbm
- **model_family**: tree
- **current_resolved_device**: cpu
- **gpu_support_rationale**: LGBMRegressor (lightgbm) has an official GPU training backend (enabled via device_type="gpu"); catalog.py tags this model 'gpu_optional'.
- **cpu_only_rationale**: n/a (library supports both CPU and GPU; CPU is the library default when no GPU kwarg is passed)
- **blocking_reason**: Pure code-wiring gap, not an environment limitation: workers._lag_regression constructs LGBMRegressor with no device parameter and never passes device_type="gpu" (or any GPU-enabling kwarg) regardless of the --device CLI setting. Confirmed by reading the full constructor body.
- **required_fix**: Add a device parameter to workers and pass device_type="gpu" conditioned on the resolved device being cuda; then empirically verify (Phase 8) that the installed lightgbm wheel actually has a GPU backend compiled in before trusting any GPU run.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `xgboost-classifier`

- **device_class**: GPU_OPTIONAL
- **framework**: xgboost
- **model_family**: tree
- **current_resolved_device**: cpu
- **gpu_support_rationale**: XGBClassifier (xgboost) has an official GPU training backend (enabled via device="cuda"); catalog.py tags this model 'gpu_optional'.
- **cpu_only_rationale**: n/a (library supports both CPU and GPU; CPU is the library default when no GPU kwarg is passed)
- **blocking_reason**: Pure code-wiring gap, not an environment limitation: factory.RuntimeModel constructs XGBClassifier with no device parameter and never passes device="cuda" (or any GPU-enabling kwarg) regardless of the --device CLI setting. Confirmed by reading the full constructor body.
- **required_fix**: Add a device parameter to factory and pass device="cuda" conditioned on the resolved device being cuda; then empirically verify (Phase 8) that the installed xgboost wheel actually has a GPU backend compiled in before trusting any GPU run.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `catboost-classifier`

- **device_class**: GPU_OPTIONAL
- **framework**: catboost
- **model_family**: tree
- **current_resolved_device**: cpu
- **gpu_support_rationale**: CatBoostClassifier (catboost) has an official GPU training backend (enabled via task_type="GPU"); catalog.py tags this model 'gpu_optional'.
- **cpu_only_rationale**: n/a (library supports both CPU and GPU; CPU is the library default when no GPU kwarg is passed)
- **blocking_reason**: Pure code-wiring gap, not an environment limitation: factory.RuntimeModel constructs CatBoostClassifier with no device parameter and never passes task_type="GPU" (or any GPU-enabling kwarg) regardless of the --device CLI setting. Confirmed by reading the full constructor body.
- **required_fix**: Add a device parameter to factory and pass task_type="GPU" conditioned on the resolved device being cuda; then empirically verify (Phase 8) that the installed catboost wheel actually has a GPU backend compiled in before trusting any GPU run.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `mlforecast-lightgbm`

- **device_class**: GPU_OPTIONAL
- **framework**: lightgbm
- **model_family**: lag_ml
- **current_resolved_device**: cpu
- **gpu_support_rationale**: LGBMRegressor (lightgbm) has an official GPU training backend (enabled via device_type="gpu"); catalog.py tags this model 'gpu_optional'.
- **cpu_only_rationale**: n/a (library supports both CPU and GPU; CPU is the library default when no GPU kwarg is passed)
- **blocking_reason**: Pure code-wiring gap, not an environment limitation: workers._mlforecast constructs LGBMRegressor with no device parameter and never passes device_type="gpu" (or any GPU-enabling kwarg) regardless of the --device CLI setting. Confirmed by reading the full constructor body.
- **required_fix**: Add a device parameter to workers and pass device_type="gpu" conditioned on the resolved device being cuda; then empirically verify (Phase 8) that the installed lightgbm wheel actually has a GPU backend compiled in before trusting any GPU run.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `stats-naive`

- **device_class**: CPU_ONLY
- **framework**: statsforecast
- **model_family**: statistical
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: Nixtla statsforecast's Naive is a Numba-JIT CPU implementation of a classical statistical model; the library has no GPU/CUDA backend for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `stats-historic-average`

- **device_class**: CPU_ONLY
- **framework**: statsforecast
- **model_family**: statistical
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: Nixtla statsforecast's HistoricAverage is a Numba-JIT CPU implementation of a classical statistical model; the library has no GPU/CUDA backend for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `stats-autoarima`

- **device_class**: CPU_ONLY
- **framework**: statsforecast
- **model_family**: statistical
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: Nixtla statsforecast's AutoARIMA is a Numba-JIT CPU implementation of a classical statistical model; the library has no GPU/CUDA backend for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `stats-autoets`

- **device_class**: CPU_ONLY
- **framework**: statsforecast
- **model_family**: statistical
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: Nixtla statsforecast's AutoETS is a Numba-JIT CPU implementation of a classical statistical model; the library has no GPU/CUDA backend for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `stats-autotheta`

- **device_class**: CPU_ONLY
- **framework**: statsforecast
- **model_family**: statistical
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: Nixtla statsforecast's AutoTheta is a Numba-JIT CPU implementation of a classical statistical model; the library has no GPU/CUDA backend for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `stats-autoces`

- **device_class**: CPU_ONLY
- **framework**: statsforecast
- **model_family**: statistical
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: Nixtla statsforecast's AutoCES is a Numba-JIT CPU implementation of a classical statistical model; the library has no GPU/CUDA backend for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `stats-croston`

- **device_class**: CPU_ONLY
- **framework**: statsforecast
- **model_family**: intermittent
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: Nixtla statsforecast's CrostonClassic is a Numba-JIT CPU implementation of a classical statistical model; the library has no GPU/CUDA backend for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `stats-tsb`

- **device_class**: CPU_ONLY
- **framework**: statsforecast
- **model_family**: intermittent
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: Nixtla statsforecast's TSB is a Numba-JIT CPU implementation of a classical statistical model; the library has no GPU/CUDA backend for this estimator.
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `nf-dlinear`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-nlinear`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-nhits`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-nbeats`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-nbeatsx`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-tide`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-tcn`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-gru`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-lstm`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-deepar`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-tft`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-patchtst`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-timesnet`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-tsmixer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-timemixer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-itransformer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-vanilla-transformer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: deep
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast correctly resolves accelerator='gpu' when self.device=='cuda' or (self.device=='auto' and torch.cuda.is_available()), confirmed by direct code read (lines 364-421 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending only a per-model 1-fold GPU probe (Phase 9) to confirm actual PyTorch Lightning GPU execution in this environment.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI (Phase 3) to forbid CPU-fallback-on-exception for this model specifically.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-rnn`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-lstm`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-gru`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-tcn`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-deepar`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-dilatedrnn`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-bitcn`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-mlp`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-nbeats`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-nbeatsx`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-nhits`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-dlinear`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-nlinear`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-tide`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-deepnpts`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-kan`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-tft`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-vanilla-transformer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-informer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-autoformer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-fedformer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-patchtst`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-itransformer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-timexer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-timesnet`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-stemgnn`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-tsmixer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-tsmixerx`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-mlp-multivariate`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-softs`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-timemixer`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-rmok`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: neuralforecast_auto
- **current_resolved_device**: cuda (when --device cuda/auto and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu'; workers._neuralforecast_auto correctly computes gpus=1 when self.device in {'auto','cuda'} and torch.cuda.is_available(), then sets accelerator='gpu' (lines 423-486 of workers.py).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none identified in code; formal eligibility pending Phase 9 1-fold probe.
- **required_fix**: none (device wiring already correct); still needs Phase 9 probe + gpu-strict CLI.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `nf-auto-hint`

- **device_class**: GPU_REQUIRED
- **framework**: neuralforecast
- **model_family**: hierarchical
- **current_resolved_device**: cpu (hardcoded)
- **gpu_support_rationale**: catalog.py tags 'gpu'; underlying AutoHINT/NBEATS architecture is the same GPU-capable PyTorch Lightning stack used by every other neuralforecast_auto model.
- **cpu_only_rationale**: n/a
- **blocking_reason**: workers._autohint hardcodes base_model_config['accelerator']='cpu' and never reads self.device at all, unlike _neuralforecast/_neuralforecast_auto. A pre-existing in-code AUDIT comment (dated 2026-07-31, referencing 'Phase 11') already flags this exact gap as deliberately deferred, not accidental. Confirmed by direct code read (lines 488-569 of workers.py).
- **required_fix**: Wire self.device into _autohint's base_model_config the same way _neuralforecast_auto does (accelerator = 'gpu' if self.device in {'auto','cuda'} and torch.cuda.is_available() else 'cpu'), then re-run a 1-fold GPU probe before treating it as formally eligible.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `autogluon-timeseries`

- **device_class**: CPU_ONLY
- **framework**: autogluon
- **model_family**: automl
- **current_resolved_device**: cpu
- **gpu_support_rationale**: AutoGluon-TimeSeries as a library CAN use GPU for some model types, but this catalog entry has no gpu/gpu_optional capability tag and workers._autogluon defaults presets='fast_training' (a CPU-only statistical/tabular model group) and explicitly maps device 'auto'->'cpu' (self.device if self.device != 'auto' else 'cpu').
- **cpu_only_rationale**: fast_training preset trains only CPU-only model families; there is no GPU model in the ensemble it selects, so certifying this entry as GPU-anything would misrepresent what actually ran.
- **blocking_reason**: Conflation of a fast-CPU smoke preset with formal GPU-capable execution (Phase 1 problem #3).
- **required_fix**: Phase 7: split into 'autogluon-timeseries-fast-cpu' (keep this entry as CPU_ONLY, fast_training) and a new, separate 'autogluon-timeseries-gpu' catalog entry with explicit GPU-only hyperparameters/num_gpus and real GPU evidence capture; do not force fast_training onto GPU.
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `darts-ensemble`

- **device_class**: CPU_ONLY
- **framework**: darts
- **model_family**: framework
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: workers._darts builds RegressionEnsembleModel([NaiveDrift(), ExponentialSmoothing()]) -- both are classical statistical components with no tensor/GPU code whatsoever (confirmed by direct code read, lines 659-690 of workers.py).
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `gluonts-deepar`

- **device_class**: GPU_OPTIONAL
- **framework**: gluonts
- **model_family**: deep_probabilistic
- **current_resolved_device**: cpu (hardcoded)
- **gpu_support_rationale**: gluonts.torch.DeepAREstimator is a PyTorch Lightning model and is GPU-capable in principle, but catalog.py only tags this model ('probabilistic',) -- it does not claim 'gpu' support, consistent with the current hardcoded-CPU implementation.
- **cpu_only_rationale**: As currently wired, this model never attempts GPU, so for THIS GPU-strict audit it must not be certified GPU-anything until the code gap below is fixed.
- **blocking_reason**: workers._gluonts hardcodes trainer_kwargs['accelerator']='cpu', with the same pre-existing AUDIT comment (dated 2026-07-31, 'Phase 11') as _autohint, flagging it as a known, deliberately-deferred gap. Confirmed by direct code read (lines 692-764 of workers.py).
- **required_fix**: Wire self.device into _gluonts's trainer_kwargs the same way _neuralforecast does; add a 'gpu' capability tag to catalog.py once fixed; then re-run a 1-fold GPU probe.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `reservoir-esn`

- **device_class**: CPU_ONLY
- **framework**: reservoirpy
- **model_family**: reservoir
- **current_resolved_device**: cpu
- **gpu_support_rationale**: none
- **cpu_only_rationale**: reservoirpy's Reservoir >> Ridge echo-state-network pipeline is a pure NumPy/CPU implementation with no CUDA backend (confirmed by direct code read, lines 766-811 of workers.py).
- **blocking_reason**: none
- **required_fix**: none
- **formal_eligibility**: True
- **allow_cpu_fallback**: True

### `chronos-bolt-tiny`

- **device_class**: GPU_OPTIONAL
- **framework**: chronos
- **model_family**: tsfm
- **current_resolved_device**: cuda (when --device cuda and CUDA available)
- **gpu_support_rationale**: catalog.py tags 'gpu_optional'; providers/chronos.py computes device_map='cuda' if self.device=='cuda' and torch.cuda.is_available() else 'cpu' (in-process, not a subprocess). Correct when device is passed as literal 'cuda' (as the orchestrator's resolved effective_device does); would silently stay on CPU if 'auto' were passed straight through without prior resolution.
- **cpu_only_rationale**: n/a
- **blocking_reason**: Not yet probed with a real GPU-evidence-capturing run this session.
- **required_fix**: none required for device logic itself; needs Phase 9 1-fold probe with the richer Phase 4 evidence schema to certify GPU_CERTIFIED rather than just cuda_available.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `chronos-2-small`

- **device_class**: GPU_OPTIONAL
- **framework**: chronos
- **model_family**: tsfm
- **current_resolved_device**: cuda (when --device cuda and CUDA available)
- **gpu_support_rationale**: Uses the same providers/chronos.py in-process provider and identical device_map resolution logic as chronos-bolt-tiny. NOTE (catalog discrepancy): catalog.py tags this entry only ('zero_shot','fine_tuning','exogenous') -- it is missing a 'gpu'/'gpu_optional' capability tag that chronos-bolt-tiny has, despite sharing the same provider code path. Flagged here rather than silently 'corrected' in catalog.py, since capability tags are declarative metadata outside this audit's stated scope of code-behavior changes.
- **cpu_only_rationale**: n/a
- **blocking_reason**: Same as chronos-bolt-tiny (not yet probed); additionally the missing capability tag means catalog-driven model selection may not even surface this as GPU-eligible.
- **required_fix**: Add 'gpu_optional' to this entry's capabilities tuple in catalog.py to match its actual provider behavior, then run the same Phase 9 probe as chronos-bolt-tiny.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `timesfm-2.5`

- **device_class**: GPU_REQUIRED
- **framework**: timesfm
- **model_family**: tsfm
- **current_resolved_device**: unresolved -- not yet probed this session
- **gpu_support_rationale**: catalog.py tags 'gpu' (mandatory, no CPU fallback allowed by library convention); run_timesfm_provider.py is a dedicated-subprocess provider sharing the same `requested_device == "cuda"` device-resolution pattern confirmed across all foundation providers.
- **cpu_only_rationale**: n/a
- **blocking_reason**: Dedicated environment (environments/timesfm) has not been probed this session -- GPU kernel compatibility on this RTX 5070 Ti (sm_120) is unconfirmed, unlike Moirai which was explicitly diagnosed and fixed.
- **required_fix**: Run the same diagnostic sequence used for Moirai (import check, CUDA tensor/matmul probe, live 1-fold GPU probe) inside environments/timesfm before any formal claim of GPU support; do not assume it works by analogy to Moirai.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `granite-ttm`

- **device_class**: GPU_OPTIONAL
- **framework**: transformers
- **model_family**: tsfm
- **current_resolved_device**: cpu (hardcoded at orchestrator level)
- **gpu_support_rationale**: catalog.py tags 'gpu_optional'; TinyTimeMixerForPrediction is a standard PyTorch (transformers) model with no architectural GPU blocker per se.
- **cpu_only_rationale**: n/a
- **blocking_reason**: scripts/run_formal_model_backtest.py lines 570-572 unconditionally force effective_device='cpu' with fallback_reason='granite_ttm_forced_cpu_env_compatibility' whenever spec.model_id=='granite-ttm', citing a past local-environment CUDA compatibility problem. This predates the torch 2.13+cu130 / sm_120 fix already applied for Moirai's near-identical 'no kernel image is available' failure, and has NOT been re-verified since. This is a distinct, additional block on top of the systemic auto-resolution pattern.
- **required_fix**: Re-run Moirai-style diagnostics (import check, CUDA tensor/matmul probe, live 1-fold GPU probe) for granite-ttm under the current torch build; only remove the hardcoded CPU force in run_formal_model_backtest.py if the probe passes. Do not assume parity with Moirai's fix without empirical confirmation.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `tirex`

- **device_class**: GPU_OPTIONAL
- **framework**: tirex
- **model_family**: tsfm
- **current_resolved_device**: unresolved -- not yet probed this session
- **gpu_support_rationale**: catalog.py tags 'gpu_optional'; run_tirex_provider.py is a dedicated-subprocess provider sharing the same requested_device=='cuda' resolution pattern.
- **cpu_only_rationale**: n/a
- **blocking_reason**: Dedicated environment (environments/tirex) has not been probed this session.
- **required_fix**: Run the Moirai-style diagnostic sequence inside environments/tirex before any formal GPU claim.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `moirai`

- **device_class**: GPU_REQUIRED
- **framework**: uni2ts
- **model_family**: tsfm
- **current_resolved_device**: cuda (verified)
- **gpu_support_rationale**: catalog.py tags 'gpu' (mandatory). Root cause of the original 'CUDA error: no kernel image is available for execution on the device' was torch 2.4.1+cu121's arch_list topping out at sm_90, incompatible with this GPU's sm_120 compute capability. FIXED this audit: environments/moirai/pyproject.toml overrides uni2ts's torch<2.5 bound with torch>=2.13 via [tool.uv] override-dependencies, relocked to torch==2.13.0+cu130 (arch_list now includes sm_120). Verified via independent CUDA tensor/matmul/synchronize probe (pass), uni2ts/Moirai2Module import check (pass), and a live 1-fold GPU probe through scripts/run_moirai_provider.py with device='cuda' (gpu_used: true, cpu_fallback: false, peak_vram_bytes: 80993280, finite predictions).
- **cpu_only_rationale**: n/a
- **blocking_reason**: none (resolved)
- **required_fix**: none remaining at the environment/kernel level; still needs Phase 3's gpu-strict CLI to formally forbid CPU fallback for this model in orchestrated runs (not yet wired).
- **formal_eligibility**: True
- **allow_cpu_fallback**: False

### `sundial`

- **device_class**: GPU_REQUIRED
- **framework**: transformers
- **model_family**: tsfm
- **current_resolved_device**: unresolved -- not yet probed this session
- **gpu_support_rationale**: catalog.py tags 'gpu' (mandatory); run_sundial_provider.py is a dedicated-subprocess provider sharing the same requested_device=='cuda' resolution pattern. Uses trust_remote_code=True (thuml/sundial-base-128m).
- **cpu_only_rationale**: n/a
- **blocking_reason**: Dedicated environment (environments/sundial) has not been probed this session; GPU kernel compatibility on sm_120 unconfirmed.
- **required_fix**: Run the Moirai-style diagnostic sequence inside environments/sundial before any formal GPU claim.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

### `tabpfn-ts`

- **device_class**: PROVIDER_BROKEN
- **framework**: tabpfn_time_series
- **model_family**: foundation_tabular
- **current_resolved_device**: n/a (fails before producing a prediction on either device)
- **gpu_support_rationale**: catalog.py tags 'gpu_optional'; expected classification after repair is GPU_OPTIONAL, but the provider currently cannot be exercised on either device.
- **cpu_only_rationale**: n/a
- **blocking_reason**: Fails on BOTH CUDA and CPU with "unsupported operand type(s) for +: 'int' and 'NoneType'" -- a provider/input-conversion defect that occurs before GPU concerns even apply, matching this audit's PROVIDER_BROKEN definition exactly. Root cause not yet located this session (src/loto/models/providers/tabpfn_ts.py exists, confirmed at line 62 with '"device": self.device,', but its full body and the NoneType error's exact origin have not been read yet).
- **required_fix**: Phase 6: locate the exact origin of the NoneType addition (checklist: forecast horizon, context length, n_estimators, random_state, device, n_jobs, frequency, timestamps, missing values, target/feature shape, quantile configuration, TabPFN regressor constructor args, package version). Provider must preserve the full traceback rather than collapsing to str(exc). Must not casually default the None value to 0 -- identify exactly which value is None and what the official API expects. After fixing, run CPU 1-fold probe -> CUDA tensor probe -> GPU-strict 1-fold probe -> 10-fold smoke in that exact order.
- **formal_eligibility**: False
- **allow_cpu_fallback**: False

