# HierarchicalForecast verification report

## Status

- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- State: `PARTIALLY_VERIFIED / HARDENED_PROMOTION_TESTS_PASS / CI_BLOCKED_RUNNER_START`
- Promotion verdict: `NOT_READY_FOR_REVIEW`

The PR remains Draft until the formal promotion gate succeeds on the exact current clean head and
GitHub Actions produces real passing steps and logs.

## Implemented scope

- actual upstream `fit_predict()` adapter execution;
- all ten registered reconcilers with grouped-hierarchy compatibility handling;
- shape, finite-value, and coherence validation;
- deterministic four-game by ten-method runtime certification;
- immutable runtime manifests, SHA-256, ZIP, and sidecar;
- no-clobber hard-link or exclusive-copy publication;
- read-only standalone transferred-package verification;
- target-machine locked provisioning and independent runtime/source/package checks;
- sealed quality and promotion gates with Git pre/post checks;
- fail-fast chaining and independent child-evidence validation.

No Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective accuracy claim is made.

## Focused evidence

| Group | Result |
|---|---:|
| existing reconciliation | 19 passed |
| ten-class matrix | 12 passed |
| runtime certification | 9 passed |
| console entries | 2 passed |
| immutable/portable package | 11 passed |
| standalone package verifier | 7 passed |
| target verification | 9 passed |
| target operator | 6 passed |
| hardened promotion gate | 11 passed |
| quality gate | 9 passed |
| **Cumulative total** | **95 passed** |

These are cumulative isolated results, not yet one formal 95-test invocation.

## Security and integrity audit findings

The initial promotion gate verified child status and hashes but did not independently re-check all
semantic claims. The hardened implementation now verifies:

- child expected Git SHA and explicit top-level Git commit;
- clean child preflight and postflight states on the same commit;
- exact quality JUnit `95/0/0` and full-suite zero failures/errors;
- exact installed target version `1.5.1`;
- runtime summary `40/40/40/0`;
- verified method partition `executed_cases=24`, `rejected_cases=16`;
- canonical child report and manifest bytes;
- report and manifest Run ID equal to the evidence-directory name;
- exact manifest and checksum coverage, uniqueness, path safety, sizes, and hashes;
- no symbolic-link components in evidence and runtime ZIP paths;
- standalone verifier identity matching target Run ID, path, and SHA-256.

The target operator now explicitly persists `git_commit` in `OPERATOR_REPORT.json` and its existing
success test asserts that value.

## Formal local command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Required local success:

```text
promotion exit                     0
promotion status                   LOCAL_GATES_VERIFIED
formal_success                     true
ready_for_review                   false
ci_required                        true
quality focused                    95/0/0
quality full failures/errors       0/0
installed version                  1.5.1
runtime expected/executed/passed   40/40/40
runtime failed                     0
method executed/rejected           24/16
standalone package verification    VERIFIED
all evidence hashes                PASS
all Git pre/post identities        PASS
```

## Evidence roots

```text
artifacts/hierarchicalforecast-runtime/<runtime-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip.sha256
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>/
```

Each root retains its own report, manifest, logs, and checksum root. Promotion evidence links the
other roots but does not replace them.

## Pending formal gates

| Gate | State |
|---|---|
| cumulative isolated focused evidence | 95 passed |
| one combined 95-test run | pending |
| Ruff format/lint | pending formal run |
| supported mypy scope | pending formal run |
| repository-wide pytest | pending formal run |
| real installed HierarchicalForecast 1.5.1 | pending |
| real 40-case execution | pending |
| real `/mnt/e` publication | pending |
| standalone verification of real ZIP | pending |
| formal promotion-gate exit 0 | pending |
| GitHub Actions real-step success | blocked by issue #61 |

## CI blocker

The current failure class remains `BLOCKED_RUNNER_START`: jobs finish with `steps=null` and no logs.
This is not Python test-failure evidence and provides no CI verification. Issue #61 remains open.

## Verdict

`NOT_READY_FOR_REVIEW`

No direct push to `main`, force push, ready transition, auto-merge, or merge has been performed.
