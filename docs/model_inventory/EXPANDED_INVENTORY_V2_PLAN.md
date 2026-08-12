# Expanded Model Inventory v2 — Implementation Expansion Plan

```text
status_class: IMPLEMENTATION_STARTED
parent_issue: #282
phase_1_issue: #284
base_main: 1df090fa34fbf1d32ec7000b25689c49e0c20074
broad_v1: 174
probabilistic_v1: 76
unified_v1: 250
holdout: CLOSED
prospective: CLOSED
```

## 1. Purpose

The current Broad v1 catalog intentionally mixes full upstream inventories for some
libraries with one-entry framework umbrellas for others. A one-entry framework row does
not prove the upstream library has only one forecasting model.

Expanded v2 is a parallel, versioned implementation inventory. It maximizes source-backed
executable implementations without changing the denominator of already-planned Broad v1
and Unified v1 campaigns.

## 2. Identity model

Expanded v2 separates two concepts:

- `algorithm_id`: the scientific algorithm identity, which may be implemented by multiple
  libraries;
- `implementation_id`: the library/runtime-specific implementation identity.

For example, DeepAR can remain one algorithm concept while NeuralForecast, GluonTS,
AutoGluon and Darts implementations are tracked independently.

This prevents both under-counting and artificial duplicate inflation.

## 3. Frozen v1 campaign boundary

Existing campaign denominators remain immutable:

| Inventory | Frozen count | Existing campaign |
|---|---:|---|
| Broad v1 | 174 | #265: 174 x 6 = 1,044 |
| Probabilistic v1 | 76 | incremental unified family |
| Unified v1 | 250 | #266: 250 x 6 = 1,500 |

Expanded v2 does not rewrite those issues retroactively.

## 4. Phase 1 — AutoGluon expansion

The repository already declares the AutoGluon source model inventory in
`src/loto/adapters/autogluon/inventory.py`.

Current source snapshot:

- 29 base model aliases/classes;
- 9 selectable ensemble names;
- 8 unique ensemble classes because `Weighted` aliases `Greedy`.

Broad v1 currently contains one umbrella row: `autogluon-timeseries`.

Expanded v2 Phase 1 replaces that umbrella **only in the parallel Expanded v2 view** with:

- 29 source-declared base implementations;
- 8 unique ensemble implementations;
- 37 total AutoGluon implementation identities.

Therefore the current derived Phase 1 count is:

```text
174 - 1 + 37 = 210 Expanded v2 implementation identities
```

The total is also computed by code; the equation above is an explanatory snapshot, not the
source of truth.

Source declaration does not set `runtime_certified=true`. Every new identity starts with
`runtime_status=NOT_RUN` until evidence proves otherwise.

## 5. Expansion roadmap

| Phase | GitHub | Linear | Scope |
|---|---|---|---|
| Umbrella | #282 | TAJ-23 | Expanded v2 governance and identity policy |
| 1 | #284 | TAJ-25 | AutoGluon 29 base + 8 unique ensembles |
| 2 | #286 | TAJ-27 | Darts source-complete forecasting inventory and routing |
| 3 | #288 | TAJ-29 | GluonTS Torch estimator expansion |
| 4 | #289 | TAJ-32 | sktime + skforecast complete inventories |
| 5 | #291 | TAJ-34 | Time-Series-Library + BasicTS upstream-complete inventories |
| 6 | #292 | TAJ-36 | Freeze Expanded v2 count and run complete six-game certification |

ReservoirPy and missing boosting/regressor implementations are tracked by the umbrella and
must be resolved before the Phase 6 count freeze.

## 6. Per-library source-completeness rule

A library expansion must use one of these evidence sources in priority order:

1. pinned upstream revision and exported/registered model classes;
2. pinned installed runtime registry;
3. pinned source manifest generated from repository files;
4. documentation only as a cross-check, never as the sole runtime-success claim.

Every implementation records source provenance and remains distinct from runtime evidence.

## 7. Capability contract

Expanded entries should progressively record, where applicable:

- library, package, class/alias and revision;
- algorithm ID and implementation ID;
- task and game compatibility;
- execution surface: shared/provider/isolated/reconciliation/not-routable;
- trainable vs zero-shot;
- exogenous/covariate support;
- probabilistic/quantile output;
- multivariate/cross-series requirements;
- CPU/GPU support and resource class;
- save/reload capability;
- dependency and license constraints;
- runtime status and failure class.

`REGISTERED != RUNTIME_CERTIFIED` remains mandatory.

## 8. Runtime/functionality acceptance

After Expanded v2 is frozen, #292 executes the derived implementation count across the six
canonical games. Every planned row must receive one explicit normalized status.

Runtime success requires evidence as applicable for:

1. dependency/import availability;
2. model construction/load;
3. declared input contract;
4. fit/update or explicit zero-shot classification;
5. inference/predict call;
6. expected output shape/horizon/position count;
7. finite required outputs;
8. expected vs observed device;
9. child PID/process tree;
10. RSS and GPU PID/VRAM where reliable;
11. CPU fallback detection;
12. save/reload/predict where declared;
13. immutable Run ID, Git/data/config hashes, logs and SHA-256 manifest.

Silent skips are forbidden.

## 9. Scientific evaluation boundary

Inventory expansion and runtime certification do not establish forecast skill.

Development-only OOF follows runtime/functionality stabilization under identical conditions:

- primary Hit@±1;
- position Hit@±1 and all-position Hit@±1;
- MAE, MSE and RMSE;
- Random, fixed, mean, median, last, frequency and statistical baselines;
- chronological folds;
- all configured seeds with mean, variance and worst values;
- prediction SHA-256 lock before actuals are read;
- multiplicity-aware paired comparisons.

Holdout remains `CLOSED`. Prospective remains `CLOSED`.

## 10. GitHub Project tracking boundary

Target Project:

`https://github.com/users/arumajirou/projects/1`

The current ChatGPT GitHub connector does not expose Projects v2 card/field mutation. The
GitHub Issues above are therefore the project-ready tracking source. Direct Project writes
must use a Projects-capable token/workflow and must fail closed when that authentication is
absent, as specified by `docs/GITHUB_PROJECT_SCHEMA.md`.

No Project-v2 update is claimed unless a Projects-capable write is actually verified.

## 11. Phase 1 verification commands

```bash
uv run python scripts/report_expanded_model_inventory.py
uv run pytest -q tests/models/test_implementation_catalog.py
uv run ruff check src/loto/models/implementation_catalog.py \
  scripts/report_expanded_model_inventory.py \
  tests/models/test_implementation_catalog.py
uv run ruff format --check src/loto/models/implementation_catalog.py \
  scripts/report_expanded_model_inventory.py \
  tests/models/test_implementation_catalog.py
```

Full repository CI remains the final gate after focused verification.
