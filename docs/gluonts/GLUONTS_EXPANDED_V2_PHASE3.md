# GluonTS Expanded v2 Phase 3

```text
tracking: GitHub #288 / Linear TAJ-29
base_main_at_implementation_start: eb988d2947994bb637dc8f0cbc40afa05570027f
inventory_status: IMPLEMENTED_IN_BRANCH
runtime_status: MAIN_REPAIR_PENDING
holdout: CLOSED
prospective: CLOSED
automatic_promotion: FORBIDDEN
```

## Purpose

Broad v1 intentionally keeps one canonical GluonTS identity, `gluonts-deepar`. That frozen scientific denominator is not the current implementation count.

Expanded v2 Phase 3 promotes the deterministic nine-model GluonTS P6 registry into separate library-specific implementation identities while leaving Broad v1 unchanged.

```text
Broad v1 total                         = 174
GluonTS Broad v1 canonical identities  = 1
Expanded v2 Phase 1 total              = 210
GluonTS P6 source-backed identities    = 9
Current Expanded v2 after Phase 3      = 174 - 2 + 37 + 9 = 218
Delta versus Broad v1                  = +44
```

The two decomposed Broad umbrellas in the current Expanded v2 implementation are AutoGluon and GluonTS. AutoGluon contributes 37 source-backed identities; GluonTS contributes 9.

## Source contract

The GluonTS identities are derived from `src/loto/adapters/gluonts/p6_registry.py`; the list is not maintained as an independent source of truth.

The registry records:

- official source tags `v0.16.3` and `v0.17.0`;
- exact upstream source paths per estimator;
- trainer kind;
- distribution mode;
- constructor profile;
- CPU resource limits;
- deterministic `registry_sha256()`.

`expanded_inventory_counts()` exposes `gluonts_registry_sha256` so the Expanded inventory can be tied back to the deterministic P6 registry.

## Expanded implementation identities

| implementation_id | class | family | P6 output/distribution | trainer |
|---|---|---|---|---|
| `gluonts-torch-deepnpts` | `DeepNPTSEstimator` | deep probabilistic | intrinsic | native epoch |
| `gluonts-torch-deepar` | `DeepAREstimator` | deep probabilistic | StudentT | Lightning |
| `gluonts-torch-tide` | `TiDEEstimator` | MLP | intrinsic | Lightning |
| `gluonts-torch-simplefeedforward` | `SimpleFeedForwardEstimator` | MLP | intrinsic | Lightning |
| `gluonts-torch-temporalfusiontransformer` | `TemporalFusionTransformerEstimator` | transformer | StudentT | Lightning |
| `gluonts-torch-wavenet` | `WaveNetEstimator` | CNN | intrinsic | Lightning |
| `gluonts-torch-dlinear` | `DLinearEstimator` | linear | intrinsic | Lightning |
| `gluonts-torch-patchtst` | `PatchTSTEstimator` | transformer | intrinsic | Lightning |
| `gluonts-torch-lagtst` | `LagTSTEstimator` | transformer | intrinsic | Lightning |

The implementation identity is library-specific. `algorithm_id` remains separate, so a scientific algorithm such as DeepAR can exist in NeuralForecast, AutoGluon and GluonTS without pretending those implementations are the same executable identity.

## Capability and evidence boundary

Every GluonTS Expanded identity records the current P6 provider surface and bounded static capabilities derived from its registry specification:

- position-series forecasting surface;
- fit and predict contract;
- save/reload lifecycle contract;
- CPU-pinned P6 resource contract;
- distribution mode;
- trainer kind;
- explicit context-length capability where supported.

The Expanded inventory deliberately does **not** infer unsupported facts from registration:

- exogenous support: not certified by the P6 inventory;
- multivariate support: not certified by the P6 inventory;
- GPU support/runtime: not certified by the P6 inventory;
- OOF accuracy: not evaluated by inventory registration;
- Holdout/Prospective: CLOSED.

Therefore the newly created Expanded identities remain:

```text
source_declared=true
runtime_status=NOT_RUN
runtime_certified=false
```

until accepted current-main runtime evidence is attached.

## Existing exact-head runtime evidence

Draft PR #309 has separate exact-head evidence on commit:

```text
edba730a4f2c944c1ccc0bee510f7ce34833b6c3
```

That evidence reports:

```text
latest lane = 9/9 VERIFIED
compat lane = 9/9 VERIFIED
P6 total = 18/18 VERIFIED
P7D evidence_state = VALID
P7D certification_status = VERIFIED
P7D verification_state = VERIFIED
p8_eligible = true
```

This is `EXACT_HEAD_VERIFIED / MAIN_PENDING`. It must not be copied into current-main Expanded identities as `runtime_certified=true` until the repair is rebased/integrated and exact-main evidence is replayed.

## Acceptance tracking for #288

| Acceptance item | State |
|---|---|
| deterministic source-backed nine-model manifest | IMPLEMENTED |
| duplicate implementation-ID rejection | IMPLEMENTED / focused test added |
| algorithm ID vs implementation ID separation | IMPLEMENTED |
| explicit provider/execution surface | IMPLEMENTED |
| explicit source/distribution/trainer/CPU capability metadata | IMPLEMENTED |
| source declaration separated from runtime certification | IMPLEMENTED |
| Expanded v2 integration | IMPLEMENTED; derived total 218 |
| Broad v1 remains 174 | PRESERVED |
| CPU lifecycle evidence | EXACT_HEAD_VERIFIED on Draft #309; current-main replay pending |
| GPU smoke where supported | NOT YET CERTIFIED |
| Holdout | CLOSED |
| Prospective | CLOSED |

Because current-main runtime integration/replay and supported GPU smoke remain open, Phase 3 should not be marked fully `DONE` solely from inventory integration.

## Verification targets

```bash
uv run --frozen --extra dev ruff check \
  src/loto/models/implementation_catalog.py \
  tests/models/test_implementation_catalog.py

uv run --frozen --extra dev pytest -q \
  tests/models/test_implementation_catalog.py \
  tests/gluonts_campaign
```

Expected inventory assertions:

```text
broad_v1=174
autogluon_expanded_total=37
gluonts_expanded_total=9
expanded_v2=218
delta_vs_broad_v1=44
by_library.gluonts=9
runtime_certified=true for new GluonTS identities = 0
```
