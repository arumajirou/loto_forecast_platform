# Expanded Model Inventory v2 — Implementation Expansion Plan

```text
status_class: IMPLEMENTATION_IN_PROGRESS
parent_issue: #282
phase_4_issue: #289
linear: TAJ-32
base_main: 45bcf60fa04fc3736e3a73760039254573abf4c8
broad_v1: 174
probabilistic_v1: 76
combined_accounting: 250
expanded_v2_current_main: 218
expanded_v2_phase4a_candidate: 244
holdout: CLOSED
prospective: CLOSED
```

## Purpose

Expanded v2 decomposes framework umbrella entries into versioned implementation identities without changing frozen Broad v1 or the existing Broad 174 × 6 campaign denominator.

`algorithm_id` is separated from library/runtime-specific `implementation_id`. Source declaration, routability, runtime certification and scientific evaluation remain different states.

## Completed expansion slices

| Slice | Broad umbrella | Expanded identities | State |
|---|---:|---:|---|
| AutoGluon | 1 | 37 | merged |
| GluonTS P6 | 1 | 9 | merged in #323 |
| skforecast Phase 4A | 1 | 27 | PR #324 candidate |

Current main after #323 derives **218**. With Phase 4A:

```text
218 - skforecast umbrella 1 + skforecast identities 27 = 244
```

Broad v1 remains **174**.

## skforecast Phase 4A source contract

```text
package = skforecast==0.23.0
upstream_tag = v0.23.0
upstream_commit = c881d5d350426985c1c31373077b7d5b620f233d
operator_evidence_head = 9fcc1274755dca64c46dc31a9a0f60a9ef1c4ebd
manifest = src/loto/models/skforecast_inventory.py
```

Pinned source review confirms all major public forecasting strategies and prevents the initial 18-row operator-evidence subset from being mistaken for source-complete coverage. The final reviewed manifest has **27** identities:

- 5 recursive regression families;
- 1 recursive classifier representative binding;
- 1 direct Ridge;
- 1 recursive multi-series Ridge;
- 1 direct multivariate Ridge;
- 1 EquivalentDate;
- 7 explicitly supported ForecasterStats implementations;
- 2 RNN variants;
- 8 explicitly listed FoundationModel IDs.

Arbitrary sklearn-compatible estimators are not multiplied across every wrapper.

Fail-closed status:

```text
OPERATOR_LOCAL_PASS                 = 15
BLOCKED_DEPENDENCY_CONFLICT         = 1
BLOCKED_INVALID_OR_EXPIRED_TOKEN    = 1
NOT_RUN                             = 10
runtime_certified=true              = 0
```

## sktime Phase 4B

Current sktime 1.0.1 evidence:

```text
discovered/importable = 141
core-compatible = 53
optional-dependency-declared = 88
formal P1 = 4
```

Before replacing the sktime umbrella, Phase 4B must freeze the exact 141-row manifest, source/revision/hash evidence, and classify independent forecasters vs wrappers/composites/adapters. Therefore #289 / TAJ-32 remains In Progress after Phase 4A.

## Roadmap

| Phase | GitHub | Linear | Scope | State |
|---|---|---|---|---|
| 1 | #284 | TAJ-25 | AutoGluon | merged |
| 2 | #286 | TAJ-27 | Darts | open |
| 3 | #288 | TAJ-29 | GluonTS | inventory merged; runtime repair separate |
| 4A | #289 | TAJ-32 | skforecast | PR #324 |
| 4B | #289 | TAJ-32 | sktime manifest/classification | next |
| 5 | #291 | TAJ-34 | Time-Series-Library + BasicTS | open |
| 6 | #292 | TAJ-36 | final freeze + six-game certification | blocked by prior phases |

## Verification

```bash
uv run python scripts/report_expanded_model_inventory.py
uv run pytest -q tests/models/test_implementation_catalog.py
uv run ruff check src/loto/models/implementation_catalog.py \
  src/loto/models/skforecast_inventory.py \
  scripts/report_expanded_model_inventory.py \
  tests/models/test_implementation_catalog.py
uv run ruff format --check src/loto/models/implementation_catalog.py \
  src/loto/models/skforecast_inventory.py \
  scripts/report_expanded_model_inventory.py \
  tests/models/test_implementation_catalog.py
```

Expected candidate invariants:

```text
broad_v1 = 174
expanded_v2 = 244
autogluon = 37
gluonts = 9
skforecast = 27
```

Inventory expansion is not forecast-skill evidence. Hit@±1 remains primary; Holdout and Prospective remain CLOSED; automatic promotion remains FORBIDDEN.
