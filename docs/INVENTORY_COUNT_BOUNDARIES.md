# Inventory Count Boundaries

```text
status_class: EXPANDED_V2_PHASE4A_CANDIDATE
as_of: 2026-08-13
repository: arumajirou/loto_forecast_platform
base_main_sha: 45bcf60fa04fc3736e3a73760039254573abf4c8
```

Broad、Expanded、discovered、runtime-certifiedの分母を混同しません。

```text
Broad count
!= committed Expanded count
!= discovered/source count
!= runtime-certified count
!= OOF-evaluated count
```

## Current candidate counts

| Library | Broad v1 | Expanded v2 candidate | Other denominator | Boundary |
|---|---:|---:|---|---|
| AutoGluon | 1 | **37** | 29 base + 8 ensembles | source declaration != runtime certification |
| GluonTS | 1 | **9** | 9 models × 2 lanes = 18 lifecycle cells | #323 merged; runtime evidence remains separate |
| skforecast | 1 | **27** | 15 operator-local PASS / 2 BLOCKED / 10 NOT_RUN | Phase 4A PR; runtime_certified=0 |
| Darts | 1 | 1 | 58 public exports | #286 open |
| sktime | 1 | 1 | 141 discovered/importable; formal P1=4 | Phase 4B remains open |
| ReservoirPy | 1 | 1 | distinct count not frozen | #294 open |

## Derived Expanded v2 total

Current main after GluonTS #323 derives 218. Phase 4A replaces the one skforecast Broad copy with 27 reviewed implementations:

```text
218 - 1 + 27 = 244
```

Equivalent full derivation:

```text
174
- AutoGluon umbrella 1 + AutoGluon 37
- GluonTS umbrella 1 + GluonTS 9
- skforecast umbrella 1 + skforecast 27
= 244
```

Broad v1 remains **174** and the current Broad six-game planner remains **1,044 = 174 × 6**.

## skforecast 0.23.0 Phase 4A

```text
package = skforecast==0.23.0
upstream_tag = v0.23.0
upstream_commit = c881d5d350426985c1c31373077b7d5b620f233d
operator_evidence_head = 9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd
```

Pinned upstream source confirms the major public forecasting surface:

- recursive exports: `ForecasterEquivalentDate`, `ForecasterRecursive`, `ForecasterRecursiveClassifier`, `ForecasterRecursiveMultiSeries`, `ForecasterStats`;
- direct exports: `ForecasterDirect`, `ForecasterDirectMultiVariate`;
- deep-learning strategy: `ForecasterRnn`;
- foundation strategy: `ForecasterFoundation` / `FoundationModel`;
- `ForecasterStats` explicitly supports seven statistical implementations;
- `FoundationModel` explicitly lists eight selectable model IDs, including three Chronos-2 IDs.

To avoid an unbounded wrapper × arbitrary-estimator Cartesian product, the pinned manifest contains 27 reviewed identities:

| Group | Count |
|---|---:|
| Recursive regression families | 5 |
| Recursive classifier representative binding | 1 |
| Direct Ridge | 1 |
| Recursive multi-series Ridge | 1 |
| Direct multivariate Ridge | 1 |
| EquivalentDate | 1 |
| ForecasterStats supported implementations | 7 |
| RNN LSTM / GRU | 2 |
| Foundation explicit model IDs | 8 |
| **Total** | **27** |

Fail-closed status:

```text
OPERATOR_LOCAL_PASS                 = 15
BLOCKED_DEPENDENCY_CONFLICT         = 1
BLOCKED_INVALID_OR_EXPIRED_TOKEN    = 1
NOT_RUN                             = 10
runtime_certified=true              = 0
```

Moirai-2 is blocked on normal dependency routability despite an override probe. TabPFN-TS v3 is blocked before checkpoint/inference by invalid/expired authentication. All source-only additions remain NOT_RUN.

## sktime Phase 4B

Current sktime 1.0.1 discovery remains:

```text
discovered/importable = 141
core-compatible = 53
optional-dependency-declared = 88
formal P1 = 4
```

Before replacing the sktime umbrella, Phase 4B must freeze the exact 141-row manifest and classify independent forecasters vs wrappers/composites/adapters. Therefore #289 / TAJ-32 remains In Progress after Phase 4A.

## Scientific boundary

Inventory expansion is not forecast skill. Hit@±1 remains primary with MAE/MSE/RMSE, position/all-position Hit@±1, mandatory baselines, chronological OOF, multi-seed mean/variance/worst and prediction SHA-256 sealing before actuals.

Holdout=CLOSED. Prospective=CLOSED. Automatic promotion/retraining/registry writes=FORBIDDEN.
