# 基本設計書 / Architecture

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

## 1. Design goals

- leakage-safe chronological evaluation;
- Hit@±1-first scientific comparison;
- six-game geometry without duplicated hard-codes;
- broad inventory and executable routing separation;
- shared and isolated provider coexistence;
- runtime evidence separated from forecast-quality evidence;
- fail-visible model × game coverage;
- prediction-before-actual sealing;
- theory-aware target semantics;
- manual promotion governance;
- pre-experiment power/MDE planning;
- immutable evidence lineage.

## 2. Canonical geometry layer

```text
src/loto/game/geometry.py
```

```text
mini      select / 5 / 1..31
loto6     select / 6 / 1..43
loto7     select / 7 / 1..37
bingo5    select / 8 / 1..40
numbers3  digits / 3 / 0..9
numbers4  digits / 4 / 0..9
```

Geometry exposes positions, universe, legality and derived outcome properties. Select and digit semantics are deliberately different.

## 3. Major components

```text
src/loto/
├── game/
│   └── geometry.py                game shape/legality authority
├── data/                           acquisition/canonicalization/access
├── features/                       as-of historical features
├── models/
│   ├── catalog_full.py             broad 174-entry forecast inventory
│   ├── catalog.py                  shared ModelSpec catalog
│   ├── factory.py                  direct candidate estimators
│   ├── workers.py                  position/foundation execution
│   └── providers/                  shared foundation providers
├── evaluation/
│   ├── protocol_v2.py              result-affecting protocol identity
│   ├── metrics.py                  geometry-general outcome metrics
│   ├── metrics_general.py          campaign metric layer
│   ├── theory_general.py           exact geometry-aware theory reference
│   ├── theory_guard.py             theory-aware configured thresholds
│   ├── power_analysis.py           paired-score MDE/power planning
│   ├── seed_summary.py             all-seed aggregation
│   └── unified_campaign.py         broad model × game development campaign
├── decoding/                        hybrid/legacy geometry-aware decoding
├── probabilistic/
│   ├── decoder.py                  MAP/WITHIN_TAU family-aware decoder
│   ├── catalog.py                  separate 72-model probabilistic catalog
│   └── ...                         runner/API/backends/native implementations
├── autogluon_campaign/
│   └── promotion_eligibility*      v1/v2 promotion evidence and rules
├── *_campaign/                      isolated library/provider lanes
├── orchestration/                   research and trusted vertical slices
├── registry/                        run/artifact/release/approval state
├── observability/                   metrics/tracing/resource monitoring
├── api/                             FastAPI surfaces
└── events/                          structured audit events
```

`environments/**` contains version-isolated provider environments and locks.

## 4. Catalog architecture

```text
catalog_full.py
  -> broad planning/inventory

catalog.py
  -> shared executable ModelSpec

factory.py / workers.py / providers/**
  -> shared runtime

*_campaign/** / adapters/** / environments/**
  -> isolated provider runtime

probabilistic/catalog.py
  -> separate Bayesian/probabilistic model universe
```

Capability stages are not collapsed:

```text
REGISTERED
!= ROUTABLE
!= RUNTIME_CERTIFIED
!= OOF_EVALUATED
!= PROMOTION_ELIGIBLE
```

## 5. Unified evaluation architecture

```text
canonical game frame
  -> geometry/data validation
  -> development/closed-holdout split
  -> chronological folds
  -> EvaluationProtocolV2
  -> mandatory baselines
  -> broad catalog × game planning
  -> route classification
       candidate -> RuntimeModel
       position/foundation -> PositionSeriesWorker/provider
       isolated/non-shared -> explicit status/provider contract
       reconciliation -> NON_STANDALONE_METHOD
  -> probability decoder or point legalisation
  -> prediction lock write/fsync/SHA-256
  -> matching actual read
  -> geometry-aware Hit@±1-first scoring
  -> all-seed aggregation
  -> per-game/cross-game summaries
  -> artifact manifest/SHA256SUMS
```

Primary CLI:

```bash
uv run loto3 campaign ...
```

`loto experiment research` and `loto3 research` are separate research surfaces and are not aliases for the unified campaign.

## 6. Metrics architecture

`evaluation.metrics.evaluate_outcomes()` accepts a `GameGeometry` and validates both actual and prediction legality before scoring.

```text
select -> hit count by set overlap
digits -> hit count by exact position equality
all -> MAE/MSE/RMSE + within-tau + all-position-within-tau
```

This is the #252 geometry-general boundary. The compatibility `evaluate_draws()` remains Loto7-oriented and delegates to the general function.

## 7. Decoder architecture

Probability-bearing candidate route:

```text
candidate binary scores
  -> per-slot normalization
  -> distribution identity
  -> family dispatch
       digits -> positional window-mass utility
       select -> legal constrained DP
  -> legal point forecast
```

Current distribution identity:

```text
row-normalized-slot-binary-probability-v1
```

Objectives include `MAP` compatibility and `WITHIN_TAU` utility. Point-only workers do not receive fabricated probability distributions.

## 8. Theory architecture

```text
theory_general.py
  -> exact game/tau IID-null reference

theory_guard.py
  -> configured semantics
       absolute
       excess_vs_iid_null
  -> implied absolute target
  -> fail-closed validation
```

The theory layer constrains interpretation but does not assert that observed lottery data are IID or non-IID.

## 9. Promotion architecture

```text
sealed Holdout score evidence
+ sealed Prospective window evidence
+ PromotionPolicy / PromotionPolicyV2
  -> schema-aware parser
  -> game identity validation (v2)
  -> theory target resolution (v2)
  -> aggregate/worst-window rules
  -> degradation rules
  -> required baseline comparisons
  -> immutable decision/rule artifacts
```

Safety boundary:

```text
ELIGIBLE_FOR_HUMAN_APPROVAL
!= PROMOTED
```

Automatic promotion, retraining and registry write are disabled by contract.

## 10. Power planning architecture

```text
pre-target score_sd + declared effect/sample count + PowerPlan
  -> adjusted_alpha = alpha / multiplicity
  -> one-sided normal critical values
  -> required_paired_draws OR minimum_detectable_effect
  -> deterministic planning evidence
```

Method identity is `paired-score-normal-approximation-v1`. The module intentionally does not pretend Hit@±1 elements are independent Bernoulli trials.

## 11. Data/time architecture

Logical layers:

```text
immutable raw source
validated canonical development data
as-of features
closed Holdout slice
sealed future Prospective prediction
later actual evidence
```

Relevant times include event/source time, availability time, ingestion time, prediction/seal time and actual read time.

## 12. Prediction/evidence architecture

Each run uses a new output directory.

Unified campaign artifacts:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/<game>.json
prediction_locks/<game>/<candidate>/seed-<seed>.json
SHA256SUMS
```

The lock is persisted and hashed before the corresponding scoring actual is read.

## 13. Runtime certification architecture

Formal runtime evidence may include:

```text
model/revision/artifact identity
environment/lock identity
load
input
inference
shape/finite output
device request/effective device
GPU PID/VRAM/utilization
CPU fallback
save/reload
cleanup/VRAM release
```

Runtime certification remains orthogonal to scientific accuracy.

## 14. Probabilistic architecture

Separate 72-model catalog provides model family metadata, native implementation registry, optional backend probing, compatibility decisions, execution profiles and run API.

```text
catalog -> compatibility -> validate config -> plan -> smoke/run
       -> status/diagnose/compare
```

Optional backend families include PyMC, NumPyro/JAX, Pyro/Torch, Stan/CmdStanPy, BlackJAX and TensorFlow Probability.

## 15. API/control plane

The platform has:

- standard `loto` CLI;
- JSON-oriented `loto3` CLI;
- authenticated local probabilistic execution API;
- registry/artifact/approval commands;
- notification/TTS surfaces;
- PostgreSQL/MLflow/telemetry optional lanes.

Control-plane availability does not automatically authorize scientific gate transitions.

## 16. Portability

- `uv`, `pyproject.toml`, `uv.lock` are root environment authorities.
- isolated providers can carry independent locks.
- Linux exact-head full CI is a repository merge gate.
- native Windows portability is a separate lane and its queued/cancelled status must not be represented as PASS.
- CUDA claims require actual effective-device evidence.

## 17. Scientific gate architecture

```text
IMPLEMENTED
-> RUNTIME_CERTIFIED
-> OOF_EVALUATED
-> HOLDOUT_EVALUATED
-> PROSPECTIVE_EVALUATED
-> PROMOTION_ELIGIBLE
-> HUMAN APPROVAL
```

A `NO_MODEL_BEATS_BASELINE` or no-champion result is architecturally valid.

## 18. Quality attributes

- reproducibility;
- auditability;
- leakage resistance;
- fail visibility;
- game-geometry correctness;
- runtime portability;
- evidence immutability;
- explicit unsupported states;
- conservative governance;
- least privilege and secret hygiene.

## 19. Non-claims

This architecture does not imply complete 174 × 6 real-data success, universal TSFM GPU support, decoder OOF superiority, Holdout/Prospective completion or production promotion.
