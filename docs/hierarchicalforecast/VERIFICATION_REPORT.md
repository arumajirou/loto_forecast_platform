# HierarchicalForecast verification report

## Report status

- Component: HierarchicalForecast reconciliation adapter, runtime certification, immutable package,
  portable publication, standalone package verifier, hardened target operator, sealed local quality
  gate, and sealed local promotion gate
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- Verification state:
  `PARTIALLY_VERIFIED / PROMOTION_GATE_TESTS_PASS / CI_BLOCKED_RUNNER_START`
- Formal promotion state: `NOT_READY_FOR_REVIEW`

The branch must remain Draft until the formal promotion gate succeeds on the current clean head and
GitHub Actions produces real passing steps and logs.

## Implemented scope

- actual upstream `fit_predict()` execution through the adapter;
- all ten registered reconciliation classes;
- grouped-hierarchy compatibility and strict-tree rejection;
- shape, finite-value, and coherence validation;
- deterministic 4-game × 10-method runtime orchestration;
- runtime artifact manifests and SHA-256;
- deterministic immutable ZIP and sidecar;
- portable no-clobber publication for filesystems without hard-link support;
- standalone read-only verification of transferred ZIPs and sidecars;
- target-machine locked provisioning;
- independent runtime, case, source, filesystem, and package verification;
- preflight and postflight Git integrity;
- sealed Ruff, mypy, focused-pytest, and full-pytest orchestration;
- sealed chaining of quality, target certification, and standalone package verification;
- immutable quality, operator, runtime, and promotion evidence roots.

This work does not evaluate or claim improvement in Hit@±1, MAE, MSE, RMSE, Holdout, or
Prospective forecasting performance.

## Focused evidence

| Test group | Result |
|---|---:|
| Existing reconciliation | 19 passed |
| Ten-class upstream matrix | 12 passed |
| Runtime certification | 9 passed |
| Console entry points | 2 passed |
| Immutable and portable package | 11 passed |
| Standalone transferred-package verifier | 7 passed |
| Hardened target verification | 9 passed |
| Hardened target operator | 6 passed |
| Sealed local promotion gate | 8 passed |
| Sealed local quality gate | 9 passed |
| **Cumulative total** | **92 passed** |

The 92 results are the sum of separate isolated runs. They are not yet one formal combined run.

## Sealed local promotion gate

Formal command:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

The command runs, in order:

```text
clean Git preflight
formal quality gate
quality SHA256SUMS and artifact-manifest verification
formal target certification with hierarchicalforecast==1.5.1
operator SHA256SUMS and artifact-manifest verification
standalone ZIP and sidecar verification
runtime Run ID, ZIP path, and ZIP SHA-256 cross-check
clean unchanged Git postflight
promotion evidence sealing
```

A failed stage prevents every later stage from running.

Successful local output is deliberately bounded:

```text
status           = LOCAL_GATES_VERIFIED
formal_success   = true
ready_for_review = false
ci_required      = true
exit             = 0
```

A local zero exit does not mark the PR ready and does not replace CI.

## Promotion-gate isolated evidence

```text
promotion-gate tests       = 8/8 PASS
compileall                 = PASS
Python lines over 100      = 0
wrapper --help             = PASS
expected Git SHA required  = PASS
remote/local blob equality = PASS
```

Tested failure paths include quality failure, quality evidence tampering, target failure,
standalone verifier failure, Run ID mismatch, and postflight Git drift.

## Formal quality requirements

The quality stage requires:

```text
quality exit          = 0
quality status        = VERIFIED
focused tests         = 92
focused failures      = 0
focused errors        = 0
full-suite failures   = 0
full-suite errors     = 0
pre/post Git commit   = unchanged and clean
quality SHA256SUMS    = PASS
```

The gate includes the publisher, standalone verifier, target modules, and promotion gate in Ruff,
compileall, mypy, and focused-test coverage.

## Formal runtime and transfer requirements

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
standalone verifier exit  = 0
standalone status         = VERIFIED
same Run ID and ZIP SHA   = PASS
```

## Current promotion gates

| Gate | Current state |
|---|---|
| adapter and ten-method contract | verified with focused tests |
| runtime orchestration and artifacts | verified with deterministic doubles |
| immutable ZIP/package controls | verified with focused tests |
| portable hard-link fallback and cleanup | package tests passed |
| standalone transferred-package verifier | 7 isolated tests passed |
| hardened target verifier/operator | 15 isolated tests passed |
| sealed promotion-gate implementation | 8 isolated tests passed |
| sealed quality-gate implementation | 9 isolated tests passed |
| cumulative focused evidence | 92 passed across separate runs |
| formal combined 92-test run | pending |
| Ruff format/lint | pending formal run |
| supported mypy scope | pending formal run |
| repository-wide pytest | pending formal run |
| real installed version 1.5.1, 40 cases | pending |
| real `/mnt/e` publication and independent re-verification | pending |
| formal promotion-gate run | pending |
| GitHub Actions real-step success | blocked by issue #61 |

## Evidence roots

```text
artifacts/hierarchicalforecast-runtime/<runtime-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip.sha256
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>/
```

The promotion root links the other evidence classes but does not replace them.

## CI blocker

The current failure class remains `BLOCKED_RUNNER_START`: jobs complete with `steps=null` and no
logs. This is not Python test-failure evidence, but it provides no CI verification. Issue #61
remains open.

## Formal verdict

`NOT_READY_FOR_REVIEW`

Before promotion, record the exact Git commit, quality/runtime/operator/promotion Run IDs, focused
and full JUnit totals, installed version, 40-case totals, publication method, standalone
verification result, ZIP SHA-256, all checksum roots, and a passing GitHub Actions run with real
steps.

No direct push to `main`, force push, ready transition, auto-merge, or merge has been performed.
