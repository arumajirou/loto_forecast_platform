# HierarchicalForecast verification report

## Report status

- Component: HierarchicalForecast reconciliation adapter, runtime certification, immutable package,
  portable publication, hardened target operator, and sealed local quality gate
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- Verification state:
  `PARTIALLY_VERIFIED / PORTABLE_PUBLICATION_TESTS_PASS / CI_BLOCKED_RUNNER_START`
- Formal promotion state: `NOT_READY_FOR_REVIEW`

The branch must remain Draft until the formal quality gate, a real installed
`hierarchicalforecast==1.5.1` run on the current clean head, and repository CI all produce usable
passing evidence.

## Implemented scope

- actual upstream `fit_predict()` execution through the adapter;
- all ten registered reconciliation classes;
- grouped-hierarchy compatibility and strict-tree rejection;
- shape, finite-value, and coherence validation;
- deterministic 4-game × 10-method runtime orchestration;
- runtime artifact manifests and SHA-256;
- deterministic immutable ZIP and sidecar;
- portable no-clobber publication for filesystems without hard-link support;
- target-machine locked provisioning;
- independent runtime, case, source, filesystem, and package verification;
- preflight and postflight Git integrity;
- sealed Ruff, mypy, focused-pytest, and full-pytest orchestration;
- JUnit count validation and immutable quality evidence.

This work does not evaluate or claim improvement in Hit@±1, MAE, MSE, RMSE, Holdout, or
Prospective forecasting performance.

## Focused evidence

| Test group | Result |
|---|---:|
| Existing reconciliation | 19 passed |
| Ten-class upstream matrix | 12 passed |
| Runtime certification | 9 passed |
| Console entry | 2 passed |
| Immutable and portable package | 11 passed |
| Hardened target verification | 9 passed |
| Hardened target operator | 6 passed |
| Sealed local quality gate | 9 passed |
| **Cumulative total** | **77 passed** |

The 77 results are the sum of separate isolated runs. They are not yet one formal combined run.

## Portable publication evidence

Formal console target:

```text
loto.reconciliation.portable_package_certification:main
```

Verified behavior:

- use a hard link when supported;
- fall back to `O_CREAT | O_EXCL` exclusive copy when hard links are unavailable;
- flush and `fsync` copied bytes;
- recompute the final ZIP SHA-256;
- create the sidecar without replacing an existing path;
- delete a partial copied ZIP after simulated failure;
- reuse only byte-identical existing evidence;
- reject and preserve different ZIP or sidecar evidence.

Published package and console subset:

```text
package tests              = 11/11 PASS
console tests              = 2/2 PASS
combined subset            = 13/13 PASS
compileall                 = PASS
Python lines over 100      = 0
remote/local blob equality = PASS
```

The package result records `publication_method=hardlink`, `exclusive_copy`, or
`reused_existing`.

## Formal local quality command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_quality_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Required result:

```text
quality exit          = 0
quality status        = VERIFIED
focused tests         = 77
focused failures      = 0
focused errors        = 0
full-suite failures   = 0
full-suite errors     = 0
pre/post Git commit   = unchanged and clean
quality SHA256SUMS    = PASS
```

The quality gate includes `portable_package_certification.py` in Ruff, compileall, mypy, and
package-test coverage.

## Formal runtime command

```bash
python3 scripts/run_hierarchicalforecast_target_certification.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Required result:

```text
operator exit             = 0
operator status           = VERIFIED
runtime status            = VERIFIED
expected/executed/passed  = 40/40/40
failed                     = 0
actual executions         = 24
grouped rejections        = 16
runtime/operator hashes   = PASS
ZIP and sidecar           = PASS
publication method        = recorded
```

## Current promotion gates

| Gate | Current state |
|---|---|
| adapter and ten-method contract | verified with focused tests |
| runtime orchestration and artifacts | verified with deterministic doubles |
| immutable ZIP/package controls | verified with focused tests |
| portable hard-link fallback and cleanup | package tests passed |
| hardened target verifier/operator | 15 isolated tests passed |
| sealed quality-gate implementation | 9 isolated tests passed |
| cumulative focused evidence | 77 passed across separate runs |
| formal combined 77-test run | pending |
| Ruff format/lint | pending formal run |
| supported mypy scope | pending formal run |
| repository-wide pytest | pending formal run |
| real installed version 1.5.1, 40 cases | pending |
| real `/mnt/e` publication | pending |
| GitHub Actions real-step success | blocked by issue #61 |

## CI blocker

Latest current-head evidence:

```text
head       = 1f42bf5cdfa29b505c76dab69971a922f78e3f9a
run        = 30993455874 / #1476
job        = 92264781066
conclusion = failure
steps      = null
logs_url   = null
```

This is `BLOCKED_RUNNER_START`, not Python test-failure evidence. Issue #61 remains open.

## Formal verdict

`NOT_READY_FOR_REVIEW`

Before promotion, record the exact Git commit, quality/runtime/operator Run IDs, focused and full
JUnit totals, installed version, 40-case totals, publication method, ZIP SHA-256, all checksum
roots, and a passing GitHub Actions run with real steps.

No direct push to `main`, force push, ready transition, auto-merge, or merge has been performed.
