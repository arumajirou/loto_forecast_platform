# Inventory Count Boundaries

```text
status_class: DARTS_PHASE2A_PLUS_PHASE4A_SOURCE_BACKED
as_of: 2026-08-13T21:30+09:00
repository: arumajirou/loto_forecast_platform
base_main_sha: 179bcbc9a51a60f0badfe7faa25f3818ab686229
```

Broad、Expanded、discovered、runtime-certifiedの分母を混同しません。

```text
Broad count
!= Expanded count
!= discovered/source count
!= runtime-certified count
!= OOF-evaluated count
```

## Current source-backed counts

| Library | Broad v1 | Expanded v2 | Other denominator | Boundary |
|---|---:|---:|---|---|
| AutoGluon | 1 | **37** | 29 base + 8 ensembles | source declaration != runtime certification |
| GluonTS | 1 | **9** | 9 models × 2 lanes = 18 lifecycle cells | #323 merged; runtime evidence remains separate |
| skforecast | 1 | **27** | 15 operator-local PASS / 2 BLOCKED / 10 NOT_RUN | #324 merged; runtime_certified=0 |
| Darts | **1** | **55** | **58 public exports** | Phase 2a source identities; Phase 2b routing/runtime open |
| sktime | 1 | 1 | 141 discovered/importable; formal P1=4 | Phase 4B remains open |
| ReservoirPy | 1 | 1 | distinct count not frozen | #294 open |

## Derived Expanded v2 total

Current main after skforecast #324 derives **244**. Darts Phase 2a replaces only the one frozen Darts Broad copy with 55 source identities:

```text
244 - Darts Broad copy 1 + Darts source identities 55 = 298
```

Equivalent full derivation:

```text
174
- AutoGluon umbrella 1 + AutoGluon 37
- GluonTS umbrella 1 + GluonTS 9
- skforecast umbrella 1 + skforecast 27
- Darts umbrella 1 + Darts source identities 55
= 298
```

Broad v1 remains **174** and the Broad six-game planner remains **1,044 = 174 × 6**.

## Darts 0.46.1 Phase 2a — 1 / 58 / 55

```text
Broad v1 umbrella                  = 1 (`darts-ensemble`)
public forecasting exports         = 58
abstract base exclusions           = 1
expired/deprecated alias exclusions= 2
Expanded source identities         = 55
```

Explicit source exclusions:

| public export | classification | replacement / reason |
|---|---|---|
| `EnsembleModel` | `ABSTRACT_BASE` | concrete ensemble implementations are tracked separately |
| `RandomForest` | `DEPRECATED_ALIAS` | `RandomForestModel` |
| `RegressionModel` | `DEPRECATED_ALIAS` | `SKLearnModel` |

Source authority:

- `src/loto/models/darts_source_inventory.py` — pinned 0.46.1 source fixture, exclusions, family classification, manifest SHA-256;
- `src/loto/models/expanded_inventory_v2.py` — overlays Darts onto the current main Expanded inventory rather than reconstructing AutoGluon/GluonTS/skforecast;
- `scripts/report_expanded_model_inventory_v2.py` — Darts-aware JSON report.

All 55 Darts identities start fail-closed:

```text
source_declared=true
source_version=0.46.1
evidence_class=SOURCE_DECLARED
routability=UNKNOWN
runtime_status=NOT_RUN
runtime_certified=false
execution_surface=darts_provider_pending
capabilities=source_declared only
```

The 58-source-export denominator, the 55 Expanded denominator, and runtime-certified count are intentionally different. Local NLinear/DLinear GPU evidence is identity-specific and is not propagated to all 55 rows.

## skforecast 0.23.0 Phase 4A

```text
package = skforecast==0.23.0
upstream_tag = v0.23.0
upstream_commit = c881d5d350426985c1c31373077b7d5b620f233d
operator_evidence_head = 9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd
```

Pinned upstream source confirms the major public forecasting surface and the merged Phase 4A manifest contains 27 reviewed identities. It deliberately avoids an unbounded wrapper × arbitrary-estimator Cartesian product.

Fail-closed status remains:

```text
OPERATOR_LOCAL_PASS                 = 15
BLOCKED_DEPENDENCY_CONFLICT         = 1
BLOCKED_INVALID_OR_EXPIRED_TOKEN    = 1
NOT_RUN                             = 10
runtime_certified=true              = 0
```

## sktime Phase 4B

Current sktime 1.0.1 discovery remains:

```text
discovered/importable = 141
core-compatible = 53
optional-dependency-declared = 88
formal P1 = 4
```

Before replacing the sktime umbrella, Phase 4B must freeze the exact 141-row manifest and classify independent forecasters vs wrappers/composites/adapters. Therefore #289 / TAJ-32 remains in progress.

## Source of truth for current Darts-aware Expanded count

The compatibility/base `implementation_catalog.py` currently reports **244** after merged AutoGluon/GluonTS/skforecast expansion. The Darts-aware composition intentionally layers on top of that current base:

```text
from loto.models.expanded_inventory_v2 import expanded_inventory_counts
```

Expected current source-backed result:

```text
base_expanded_v2=244
expanded_v2=298
delta_vs_broad_v1=124
darts_public_exports=58
darts_expanded_total=55
```

The compatibility/base count and Darts-aware count are shown separately until the Darts overlay is folded into the monolithic compatibility catalog in a later safe refactor. `scripts/report_expanded_model_inventory_v2.py` is the Darts-aware report entrypoint for Phase 2a.

## Scientific boundary

Inventory expansion is not forecast skill. Hit@±1 remains primary with MAE/MSE/RMSE, position/all-position Hit@±1, mandatory baselines, chronological OOF, multi-seed mean/variance/worst and prediction SHA-256 sealing before actuals.

Holdout=CLOSED. Prospective=CLOSED. Automatic promotion/retraining/registry writes=FORBIDDEN.
