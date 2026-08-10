# Current Verification Report

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
scope: current functional merge sequence + capability/scientific boundary
```

## Verdict

```text
UNIFIED_CAMPAIGN=MERGED
FAMILY_AWARE_WITHIN_TAU_DECODER=MERGED
GEOMETRY_GENERAL_METRICS=MERGED_AND_EXACT_HEAD_CI_VERIFIED
THEORY_AWARE_PROMOTION_V2=MERGED_AND_EXACT_HEAD_CI_VERIFIED
POWER_MDE_PLANNING=MERGED_AND_EXACT_HEAD_CI_VERIFIED
HOLDOUT=NOT_OPENED_BY_THIS SEQUENCE
PROSPECTIVE=NOT_OPENED_BY_THIS_SEQUENCE
AUTOMATIC_PROMOTION=FORBIDDEN
CHAMPION=NOT_CLAIMED
```

## Recent merge evidence

| PR | Merge SHA | Verification boundary |
|---|---|---|
| #248 | `aae45ba9294499f51cc5f1564de1c6ccf5814230` | unified six-game model×game campaign merged |
| #249 | `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f` | MAP/WITHIN_TAU select decoder merged |
| #250 | `8430d9f507ba735bf1df69930e057c974752bfdb` | candidate probability family routing merged after current-base Linux full CI |
| #251 | `5469410c4af679369ab65241c97ff4c4eaab39f2` | prior documentation refresh merged |
| #252 | `8c87356d6aeb776e47c06635592071a6a54014fd` | geometry-general metrics; review fixes; final exact-head Linux full CI success |
| #253 | `5c44cc866af36f3bbb44582263ff54bf392c3f10` | promotion v2; sealed game identity; theory target; final current-base Linux full CI success |
| #254 | `2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8` | power/MDE; final head `218fa3b4...`; Linux run `31382711427` passed all 33 steps against current-base merge ref |

## #252 verification summary

Review/race gates identified and corrected:

- digit games must count exact positional hits rather than unordered set product;
- geometry-literal guard exceptions must be explicitly inventoried rather than broadly excluded;
- Ruff formatting changes were applied before final CI.

Final Linux exact-head/current-base CI passed format, lint, compile, full pytest, repository-clean and cleanup before squash merge.

## #253 verification summary

Review gates identified and corrected:

- theory-aware excess target must be converted to `implied_absolute_target` before rule comparison;
- v2 artifacts must be generated/verified under v2 schema rather than interpreted as v1;
- sealed scoring evidence must carry game identity and match policy game;
- current v2 promotion tau remains fixed to 1;
- automatic promotion/retraining/registry writes remain false.

Final CI verified the PR merge ref against #252-containing main. All review threads were resolved before squash merge.

## #254 verification summary

Initial CI found an E501 lint failure; it was corrected.

Review gates then added:

- explicit positive-integer validation for power-curve draw counts, including bool rejection;
- `target_power > adjusted_alpha` validation so the normal critical-value sum cannot yield an invalid negative MDE planning regime;
- regression tests for boundary and multiplicity behavior.

Final head:

```text
218fa3b44a0b375b8e6df048f5659d00124e4740
```

Final Linux run:

```text
31382711427 = SUCCESS
```

The job passed all 33 reported steps, including:

```text
runner identity
checkout
uv/Python environment
CPU PyTorch alignment
dependency install
Ruff format
Ruff lint
compileall
full pytest
repository-clean verification
cleanup
```

The checkout log showed the current-base merge ref:

```text
Merge 218fa3b4... into 5c44cc86...
```

#254 was then squash merged to `2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8`.

## Current code-grounded capability boundary

Verified by source inspection for this documentation refresh:

- six canonical game geometries;
- 174-entry broad forecast inventory;
- narrower shared `ModelSpec` execution catalog;
- shared candidate/position/foundation provider routing;
- separate isolated AutoGluon/BasicTS/Time-Series-Library/Merlion/sktime style lanes;
- 72-model probabilistic catalog and command surface;
- current unified campaign CLI/resource controls;
- geometry-general metrics;
- theory-aware threshold semantics;
- promotion v1/v2 schema split and manual-only safeguards;
- paired-score MDE/power planning.

## Runtime evidence boundary

Repository TSFM aggregate file currently records:

```text
total_models=21
runtime_certified_models=19
```

This is point-in-time runtime evidence for exact identities. It is not a six-game OOF result.

## Scientific boundary

This verification report does not certify:

- completion of a real immutable six-game 174 × 6 campaign;
- universal model/runtime success;
- all-model GPU success;
- decoder real-data OOF gain;
- non-IID lottery structure;
- Holdout success;
- Prospective success;
- champion selection;
- production promotion.

Runtime, scientific evaluation, promotion governance and documentation verification remain distinct evidence classes.

## Historical report handling

Root `VERIFICATION_REPORT.md` remains preserved historical evidence. Current readers should use this file and `docs/STATUS.md` for the latest audited documentation snapshot rather than rewriting old observations.
