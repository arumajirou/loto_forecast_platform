# HierarchicalForecast verification report

## Report status

- Component: HierarchicalForecast reconciliation adapter, runtime certification, immutable package,
  hardened target-machine operator, and sealed local quality gate
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- Verification state:
  `PARTIALLY_VERIFIED / QUALITY_GATE_TESTS_PASS / CI_BLOCKED_RUNNER_START`
- Formal promotion state: `NOT_READY_FOR_REVIEW`

The branch must remain Draft until the formal quality gate, a real installed
`hierarchicalforecast==1.5.1` run, and repository CI all produce usable passing evidence.

## Implemented scope

- actual upstream `fit_predict()` execution through the adapter;
- all ten registered reconciliation classes;
- grouped-hierarchy compatibility and strict-tree rejection;
- shape, finite-value, and coherence validation;
- deterministic 4-game × 10-method runtime orchestration;
- runtime artifact manifests and SHA-256;
- deterministic immutable ZIP and sidecar;
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
| Immutable package | 11 passed |
| Hardened target verification | 9 passed |
| Hardened target operator | 6 passed |
| Sealed local quality gate | 9 passed |
| **Cumulative total** | **77 passed** |

The 77 results are the sum of separate isolated runs. They are not yet one formal combined run.

## Latest implementation evidence

The quality-gate implementation adds:

```text
scripts/hierarchicalforecast_target/quality_gate.py
scripts/run_hierarchicalforecast_quality_gate.py
tests/test_reconciliation_quality_gate.py
docs/hierarchicalforecast/QUALITY_GATE.md
```

Verified against the exact published Git blobs:

```text
quality-gate isolated tests  = 9/9 PASS
compileall                   = PASS
Python lines over 100 chars  = 0
wrapper --help               = PASS
expected Git SHA required    = PASS
remote/local blob equality   = PASS
```

The quality gate requires exact focused JUnit evidence:

```text
tests=77, failures=0, errors=0
```

It runs repository-wide pytest only after locked sync, dependency check, Ruff, compileall, mypy,
and the focused suite pass.

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
```

## Current promotion gates

| Gate | Current state |
|---|---|
| adapter and ten-method contract | verified with focused tests |
| runtime orchestration and artifacts | verified with deterministic doubles |
| immutable ZIP/package controls | verified with focused tests |
| hardened target verifier/operator | 15 isolated tests passed |
| sealed quality-gate implementation | 9 isolated tests passed |
| cumulative focused evidence | 77 passed across separate runs |
| formal combined 77-test run | pending |
| Ruff format/lint | pending formal run |
| supported mypy scope | pending formal run |
| repository-wide pytest | pending formal run |
| real installed version 1.5.1, 40 cases | pending |
| GitHub Actions real-step success | blocked by issue #61 |

## CI blocker

The current GitHub Actions failure mode remains `BLOCKED_RUNNER_START`: jobs complete with
`steps=null` and no logs. This is not Python test-failure evidence, but it provides no CI
verification. Issue #61 remains open.

## Formal verdict

`NOT_READY_FOR_REVIEW`

Before promotion, record in this report:

- exact Git commit;
- quality Run ID and `SHA256SUMS`;
- focused and full JUnit totals;
- runtime and operator Run IDs;
- installed HierarchicalForecast version;
- 40-case totals and method partition;
- runtime ZIP SHA-256;
- passing GitHub Actions run and job IDs.

No direct push to `main`, force push, ready transition, auto-merge, or merge has been performed.