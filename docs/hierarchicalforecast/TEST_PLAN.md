# HierarchicalForecast test plan

## Objective

Verify the reconciliation adapter, deterministic 40-case runtime harness, immutable package,
standalone verifier, target operator, local quality gate, and hardened local promotion gate in PR
#48. Test doubles validate contracts but never replace real installed
`hierarchicalforecast==1.5.1` execution.

## Required order

1. adapter tests;
2. ten-method state matrix;
3. runtime certification tests;
4. console-entry tests;
5. immutable and portable package tests;
6. standalone package-verifier tests;
7. target runtime/package/source verification tests;
8. target operator and Git-control tests;
9. hardened promotion-gate tests;
10. quality-gate tests;
11. formal promotion gate;
12. GitHub Actions with real steps.

Full repository pytest remains the last local quality command.

## Focused contract

| File/group | Isolated evidence |
|---|---:|
| existing reconciliation | 19 passed |
| ten-class upstream matrix | 12 passed |
| runtime certification | 9 passed |
| console entry points | 2 passed |
| immutable and portable package | 11 passed |
| standalone package verifier | 7 passed |
| target runtime/package/source verification | 9 passed |
| target operator | 6 passed |
| hardened promotion gate | 11 passed |
| quality gate | 9 passed |
| **Total** | **95 passed** |

The 95 results are cumulative across isolated runs. Formal acceptance requires one combined JUnit
result:

```text
tests=95, failures=0, errors=0
```

## Hardened promotion-gate tests

The 11 promotion tests cover:

- complete success and sealed promotion evidence;
- mandatory expected Git SHA;
- quality fail-fast behavior;
- modified quality evidence after sealing;
- child quality Git identity mismatch;
- focused JUnit count mismatch;
- target fail-fast behavior;
- installed version mismatch;
- standalone verifier failure;
- runtime Run ID mismatch;
- postflight Git drift.

The existing six operator tests also assert that the successful operator report persists the exact
`git_commit` used for certification.

## Formal command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

## Formal quality requirements

```text
locked sync                         PASS
uv pip check                        PASS
Ruff format                         PASS
Ruff lint                           PASS
compileall                          PASS
supported mypy scope                PASS
focused JUnit                       95/0/0
full JUnit failures/errors          0/0
quality Git pre/post                same clean commit
quality manifest and SHA256SUMS     PASS
```

## Formal runtime requirements

```text
installed version                   1.5.1
runtime expected/executed/passed    40/40/40
runtime failed                      0
method partition executed/rejected  24/16
operator Git pre/post               same clean commit
runtime/operator hashes             PASS
ZIP and sidecar                     PASS
standalone verifier                 VERIFIED / exit 0
cross-stage Run ID/path/SHA          PASS
```

## Independent promotion checks

The promotion gate must independently reject:

- child `VERIFIED` reports from another Git commit;
- noncanonical child report or manifest bytes;
- manifest Run ID inconsistent with the directory name;
- incomplete, duplicated, unsafe, or mismatched checksum rows;
- focused counts other than 95;
- a full suite with failures or errors;
- a target version other than 1.5.1;
- a runtime summary other than 40/40/40/0;
- a method partition other than 24/16;
- standalone verification for another Run ID, path, or ZIP SHA.

## GitHub Actions

Issue #61 tracks the zero-step runner-start blocker. A job with `steps=null` and no logs is not
code-validation evidence. The PR remains Draft until an Actions run has real passing checkout,
setup, dependency, Ruff, compileall, and pytest steps.

## Promotion decision

A zero local promotion exit still returns `ready_for_review=false` and `ci_required=true`. No
Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective improvement is claimed by this runtime-control work.
