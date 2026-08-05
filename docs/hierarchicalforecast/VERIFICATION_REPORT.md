# HierarchicalForecast verification report

## Status

- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- State: `PARTIALLY_VERIFIED / LOCK_CONTRACT_TESTS_PASS / CI_BLOCKED_PRE_RUN`
- Promotion verdict: `NOT_READY_FOR_REVIEW`
- Canonical CI blocker: issue #58
- PR-specific CI dependency: issue #61

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
- TOML-based dependency and lock validation before provisioning;
- fail-fast chaining and independent child-evidence validation.

No Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective accuracy claim is made.

## Locked dependency audit

Source inspection confirms:

```text
project requires-python = >=3.11,<3.14
uv.lock requires-python = >=3.11, <3.14
full declaration         = hierarchicalforecast>=1.0
locked package version   = 1.5.1
Python 3.13 wheel         = present in uv.lock
dev tools                = pytest, pytest-cov, Ruff, mypy, Pydantic
.gitignore                = .venv/ and /artifacts/ ignored
```

The broad declaration is not presented as an exact pin. Formal success depends on `uv sync
--locked` and a standard-library validator requiring the lock to resolve only version 1.5.1. The
validator records SHA-256 values for both `pyproject.toml` and `uv.lock`.

Isolated verification:

```text
lock 1.5.1 accepted
lock 1.5.0 mutation rejected
quality-gate tests 9/9 passed
compileall PASS
Python lines over 100 = 0
published Git blobs match tested inputs
```

A formal validator execution against the actual target checkout remains pending.

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
| quality gate, including dependency drift rejection | 9 passed |
| **Cumulative total** | **95 passed** |

These are cumulative isolated results, not yet one formal 95-test invocation.

## Formal local command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

The formal wrapper first validates the lock contract. The quality child validates it again and
seals the dependency result. Target certification then independently checks the installed
distribution version.

Required local success:

```text
promotion exit                     0
promotion status                   LOCAL_GATES_VERIFIED
formal_success                     true
ready_for_review                   false
ci_required                        true
dependency locked version          1.5.1
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
| dependency validator isolated mutation test | passed |
| cumulative isolated focused evidence | 95 passed |
| formal dependency validation on target checkout | pending |
| one combined 95-test run | pending |
| Ruff format/lint | pending formal run |
| supported mypy scope | pending formal run |
| repository-wide pytest | pending formal run |
| real installed HierarchicalForecast 1.5.1 | pending |
| real 40-case execution | pending |
| real `/mnt/e` publication | pending |
| standalone verification of real ZIP | pending |
| formal promotion-gate exit 0 | pending |
| GitHub Actions real-step success | blocked by canonical issue #58 |

## CI blocker evidence

The repository is private and `.github/workflows/ci.yml` contains real steps on
`runs-on: ubuntu-latest`. Independent PRs #55, #56, #57, and #48 reproduce the same pre-run
failure. The latest PR #48 observation is:

```text
head                    a97b5f58367e423625678debf6c7b49d7eca6821
workflow run            31001553962 / #1869
job                    92291396321
conclusion             failure
configured steps       present
API step list          empty
job log                404 BlobNotFound
artifacts              none
commit statuses        none
```

The supported classification is `CI_BLOCKED_PRE_RUN / REPOSITORY_OR_ACCOUNT_INFRASTRUCTURE`.
This is not Python test-failure evidence. Issue #58 is the canonical owner-action tracker; issue
#61 records only PR #48's dependency. Unchanged zero-step heads should not generate repeated
reruns or duplicate comments.

## Verdict

`NOT_READY_FOR_REVIEW`

No direct push to `main`, force push, ready transition, auto-merge, or merge has been performed.
