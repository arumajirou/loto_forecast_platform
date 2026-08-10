# Library runtime capabilities — code/evidence audit

> **Audit base:** `main@0f7585bca90fe9c1578909018a2dc24fcfdc12cb`  
> **Audited:** 2026-08-10 16:47 JST  
> **Scope:** non-TSFM framework/provider lanes that are easy to miss when only reading the 174-entry broad catalog.

## Status vocabulary

```text
IMPLEMENTED
  code/provider/worker exists

CONTRACT_VERIFIED
  project-side contracts/tests executed

RUNTIME_VERIFIED
  actual third-party package/runtime executed for an exact identity/scope

SHARED_ROUTABLE
  normal shared worker/research path can invoke it

ISOLATED_ROUTABLE
  dedicated provider/campaign entrypoint can invoke it

OOF_EVALUATED
  real leakage-safe OOF actually executed
```

A later status is never inferred from an earlier one.

## Current capability matrix

| library/framework | current code path | routing status | strongest evidenced runtime state | important boundary |
|---|---|---|---|---|
| AutoGluon TimeSeries | `environments/autogluon-timeseries/**`, `scripts/run_autogluon_timeseries_provider.py`, shared `workers.py` | **SHARED_ROUTABLE + ISOLATED_ROUTABLE** | **RUNTIME_VERIFIED** AutoGluon 1.5.0, 7/7 CPU/fallback scenarios; shared Naive fit/save/load re-predict verified | positive GPU certification not established by PR #237 |
| Time-Series-Library | `src/loto/time_series_library_campaign/**` | **ISOLATED_ROUTABLE** | **RUNTIME_VERIFIED** for 9 pinned CPU model lanes | exact isolated Torch 2.9.1 environment remained pending in the original certification scope; not shared `PositionSeriesWorker` |
| BasicTS | `src/loto/basicts_campaign/**`, `scripts/run_basicts_provider.py` | **ISOLATED_ROUTABLE** | **CONTRACT_VERIFIED**; current/legacy provider API and full BasicTS campaign tests pass | original merged P0 explicitly retained `REAL_BASICTS_RUNTIME_PENDING`; optional real BasicTS smoke was skipped |
| HierarchicalForecast | `src/loto/reconciliation/hierarchy.py` plus certifier/verifier CLI | reconciliation route, not normal model worker | **RUNTIME_VERIFIED** real `hierarchicalforecast==1.5.1` smoke for BottomUp, MinTrace, OptimalCombination | ten methods implemented, but not every method is valid for grouped/non-strict hierarchy |
| sktime | `src/loto/sktime_campaign/**`, isolated environment/scripts | **ISOLATED_ROUTABLE** | **IMPLEMENTED / CONTRACT_VERIFIED** P0-P5 machinery | merged PR #52 explicitly retained real target-runtime execution pending; not a shared `PositionSeriesWorker` branch |
| Merlion | `src/loto/merlion_campaign/**` | **ISOLATED_ROUTABLE** | **IMPLEMENTED / CONTRACT_VERIFIED** bootstrap/provenance/runtime contracts | merged Merlion work retained real target-host Arima/ETS/MSES runtime pending; native Windows bootstrap fails closed where unsupported |
| Darts | shared `PositionSeriesWorker._darts()` | **SHARED_ROUTABLE** | implementation plus focused repository tests | exact full provider/runtime certification should be read separately; worker builds RegressionEnsembleModel over NaiveDrift + ExponentialSmoothing |
| GluonTS | shared `PositionSeriesWorker._gluonts()` | **SHARED_ROUTABLE** | implementation plus focused repository tests | shared trainer hard-codes CPU; CUDA/auto request is not honored by this path |
| ReservoirPy | shared `PositionSeriesWorker._reservoir_esn()` | **SHARED_ROUTABLE** | implementation plus focused repository tests | per-position ESN; no claim here of formal OOF superiority |
| StatsForecast | shared worker + dedicated `src/loto/statsforecast/**` certifier contracts | **SHARED_ROUTABLE** for selected IDs | shared execution code exists; exact 2.1.1 all-41 package certification was historically blocked/pending | 41 broad registrations are not 41 current shared research IDs |
| MLForecast | shared `PositionSeriesWorker._mlforecast()` | **SHARED_ROUTABLE** for Ridge/LightGBM IDs | executable worker implementation | broad 8 AutoMLForecast inventory is a different surface from two shared IDs |
| NeuralForecast | root dependency + shared worker + local extensions | **SHARED_ROUTABLE** for fixed/official AutoModel subset | real package is exercised in repository tests; model-by-model certification differs | 37 broad fixed registrations != all 37 proven through one shared wrapper; local AutoSegRNN/AutoFreTS remain inactive |

## AutoGluon — strongest shared integration evidence

Merged PR #237 is the current shared-integration proof.

It records prerequisite real runtime certification:

```text
AutoGluon TimeSeries=1.5.0
Python=3.12.13
7/7 scenarios=VERIFIED
failed=0
blocked=0
```

Scenarios cover:

```text
Naive fit/save/load
Theta
fast_training preset
Naive+Theta ensemble
bounded SeasonalNaive HPO
intentional CUDA-to-CPU fallback
```

The merged shared worker uses protocol v2 by default and executes the committed isolated lock through:

```text
uv run --project environments/autogluon-timeseries --locked ...
```

The authoritative shared-worker verifier additionally executed real Naive fit/predict/save and persisted load/predict in separate PIDs. Positive GPU inference was explicitly not claimed.

## Time-Series-Library — nine real pinned CPU lanes

Merged PR #54 is stronger than a provider skeleton. It records these nine pinned CPU models as verified:

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

For the certified lanes the evidence contract includes:

```text
pinned upstream source identity
construction
bounded fit
finite prediction/state
atomic persistence
separate-process reload
strict state loading
prediction round-trip equality
```

FiLM has especially concrete retained evidence:

```text
prediction_shape=[2,2,3]
fit_pid=2542
load_pid=2570
cpu_fallback=false
max_abs_replay_error=0.0
prediction_sha256=8a5badde08d4e9d2daff169794232fe48303a72429eec4d821e357a5186b4b36
runtime=Python 3.13.5 / Torch 2.10.0+cpu / NumPy 2.3.5 / SciPy 1.17.0
```

The same PR found 41 upstream modules exposing `class Model`, but only nine were CPU-certified. The other 32 remained pending/deferred/dependency-blocked. Therefore “Time-Series-Library integrated” must not be rewritten as “all upstream models runtime-certified”.

Known examples from that evidence:

```text
Koopa=DEFERRED_REQUIRES_DATA_PROVIDER_CONSTRUCTION
MICN=EXECUTION_PENDING_MULTIFILE_CLOSURE
TimesNet=EXECUTION_PENDING_MULTIFILE_CLOSURE
PAttn=BLOCKED_MISSING_REFORMER_PYTORCH
WPMixer=BLOCKED_MISSING_PYWT
```

## BasicTS — provider is real, target runtime certification is not complete

Merged PR #56 introduced the isolated BasicTS 1.1.0 / revision `c2bb6e31e591167e84459775a21a62e70a5893ce` provider and formal DLinear P0 contracts. Current code still exposes:

```text
identity
validate_config
compile_dataset
construct_forward_save_load_smoke
```

The merged evidence is intentionally conservative:

```text
LOCAL_BASICTS_MODULE_CLOSURE_CONTRACT_PASS
REAL_BASICTS_RUNTIME_PENDING
```

The optional real BasicTS smoke was **skipped and not counted as success**.

Merged PR #214 later restored compatibility lost in integration and verified current + legacy provider APIs, full `tests/basicts_campaign` (one pre-existing skip, zero failures), chronology, Holdout non-materialization, import fail-closed behavior and Hit@±1 metric aliases. That proves the current repository contracts are healthy; it still does not retroactively turn the skipped real upstream target-host runtime into a PASS.

Therefore current documentation should use:

```text
BasicTS=IMPLEMENTED + ISOLATED_ROUTABLE + CONTRACT_VERIFIED
real upstream target runtime=NOT PROVEN COMPLETE BY MERGED EVIDENCE
```

## HierarchicalForecast — real package smoke exists

Merged PR #213 restored the real upstream wrapper and verified `hierarchicalforecast==1.5.1` in an isolated verifier.

Real methods executed:

```text
BottomUp             VERIFIED  coherence_error=0.0
MinTrace             VERIFIED  coherence_error=0.0
OptimalCombination   VERIFIED  coherence_error=0.0
```

Current source implements ten upstream classes and explicitly checks:

```text
strict hierarchy compatibility
sparse/dense summing matrix
required in-sample evidence
constructor failures
fit_predict failures
finite outputs
shape
coherence
```

This is runtime evidence for the wrapper and the three tested methods. It is not proof that all ten methods work on every grouped lottery hierarchy.

## sktime — very broad implemented lifecycle, target execution still separate

Merged PR #52 added a large isolated sktime lifecycle:

```text
P0 dynamic inventory + bounded Naive lifecycle contract
P1 four-model classic smoke matrix
P2 chronological Train/Validation benchmark
P3 Train-contained rolling-origin OOF + multi-seed aggregation + Holdout prediction lock
P4 post-lock Holdout scoring
P5 Prospective pre-actual prediction lock + post-reveal monitoring
```

It also implements Hit@±1-first metrics, baselines, prediction sealing and no-best-seed-only rules.

However the same merged PR explicitly states:

```text
REAL_TARGET_RUNTIME_EXECUTION_PENDING
```

and does not claim real target-host P0-P5, real-data metrics, baseline superiority or shared worker/catalog integration. The current main code should therefore be described as a substantial isolated framework/evaluation implementation, not a completed real Prospective certification.

## Merlion — isolated because of dependency incompatibility

Merged Merlion integration work uses a separate environment because Merlion requires NumPy `<2.0` while the root project requires NumPy `>=2.0`.

Implemented scope includes:

```text
strict provider protocol
resumable bootstrap
package/source/hash provenance
CPU lifecycle contracts for Arima / ETS / MSES
separate-process save/load/re-predict certification machinery
license/lock admission gates
SHA-256 evidence packaging
```

The merged evidence retained real target-host runtime as pending. Later PR #184 hardened native Windows behavior to fail closed rather than claiming readiness for a Bash-only bootstrap. Therefore Merlion is implemented/provider-routable but should not be labeled runtime-certified without a later exact target-run artifact.

## Darts

The shared worker is concrete code, not a catalog placeholder:

```text
per position:
  NaiveDrift
  ExponentialSmoothing
  -> RegressionEnsembleModel
  -> fit()
  -> predict(1)
```

This makes Darts shared-routable when its optional dependency is installed. Formal model comparison still requires the normal protocol/OOF evidence.

## GluonTS

The shared worker constructs and trains:

```text
DeepAREstimator
StudentTOutput
ListDataset
```

but the current trainer sets:

```text
accelerator="cpu"
devices=1
```

The source itself notes this is not reconciled with requested `cuda/auto`. Any documentation saying “GluonTS GPU supported through the shared worker” would therefore be false at this audit point.

## ReservoirPy

The shared worker builds an ESN per position:

```text
Reservoir(seed=seed+position)
>> Ridge
fit
run
```

and takes the final one-step output. It is a real dispatch branch, distinct from broad catalog registration.

## StatsForecast

There are two relevant surfaces:

1. shared `PositionSeriesWorker` for the selected shared IDs;
2. dedicated `src/loto/statsforecast/**` exact-runtime certification machinery.

The historical exact-2.1.1 certifier PR defined a 41-model runtime matrix, save/load lifecycle and evidence bundles, but its target package execution was blocked because the exact package could not be installed in that environment. Current shared code can still execute StatsForecast when the dependency is present; do not use the old blocked all-41 certifier as proof that all 41 were runtime-certified.

## MLForecast

Current normal worker has concrete paths for:

```text
mlforecast-ridge
mlforecast-lightgbm
```

with lag features and horizon-1 prediction. This is distinct from the broad eight-entry AutoMLForecast inventory.

## NeuralForecast

NeuralForecast 3.2.0 is a root dependency, and standard repository tests exercise real NeuralForecast/PyTorch code paths. The shared worker dynamically constructs fixed models and official AutoModels.

Still, the repository deliberately has model-specific/runtime-specific exceptions and local extensions. Therefore the correct statement is:

```text
NeuralForecast framework path=real and shared-routable
all broad 37 fixed models uniformly runtime-certified through this wrapper=false
all local extensions active/registered=false
```

For example, AutoSegRNN and AutoFreTS local modules are explicitly inactive; their prior PRs also stated real NeuralForecast/Ray/Optuna runtime pending and registration out of scope.

## Scientific boundary

None of the statuses above substitutes for the formal forecast-quality protocol. Runtime-verified libraries/models must still pass the same chronological OOF, required baselines, complete seed aggregation, Hit@±1-first comparison and prediction-seal rules before any accuracy/champion/promotion claim.