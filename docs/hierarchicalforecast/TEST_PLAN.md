# HierarchicalForecast test plan

## Objective

Verify the reconciliation adapter, deterministic 40-case runtime harness, immutable runtime
package, hardened target-machine operator, and sealed local quality gate introduced by PR #48.

A test double never replaces real installed `hierarchicalforecast==1.5.1` execution.

## Required order

Run the least expensive and most diagnostic checks first:

1. adapter contract;
2. all-ten-method state matrix;
3. runtime certification;
4. console entry point;
5. immutable runtime package;
6. hardened target runtime/package verification;
7. hardened target operator control;
8. sealed local quality-gate tests;
9. formal local quality gate: sync, Ruff, compileall, mypy, focused pytest, full pytest;
10. real installed-package target certification;
11. GitHub Actions verification.

The repository-wide pytest step must remain last among local quality commands.

## Focused test contract

| File | Scope | Current isolated evidence |
|---|---|---:|
| `tests/test_reconciliation.py` | adapter execution and validation | 19 passed |
| `tests/test_reconciliation_upstream_matrix.py` | all ten methods and state partition | 12 passed |
| `tests/test_reconciliation_runtime_certification.py` | 40-case orchestration and artifacts | 9 passed |
| `tests/test_reconciliation_console_script.py` | registered entry point | 2 passed |
| `tests/test_reconciliation_package_certification.py` | immutable ZIP and tamper rejection | 11 passed |
| `tests/test_reconciliation_target_machine_certification.py` | runtime/package/source verification | 9 passed |
| `tests/test_reconciliation_target_operator.py` | target operator and Git controls | 6 passed |
| `tests/test_reconciliation_quality_gate.py` | quality ordering, JUnit, failure and Git controls | 9 passed |
| **Total** | separate isolated runs | **77 passed** |

The value 77 is cumulative evidence across separate isolated runs. It is not yet one combined
pytest invocation.

## Formal quality gate

Run from a clean checkout of the exact PR head:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_quality_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

The runner performs:

```text
uv sync --extra dev --extra full --locked
uv pip check
Ruff format --check
Ruff check
compileall
mypy on the reconciliation/target scope
focused pytest with JUnit XML
repository-wide pytest with JUnit XML
postflight Git verification
SHA-256 evidence sealing
```

Focused JUnit acceptance is exact:

```text
tests=77, failures=0, errors=0
```

The full-suite JUnit must report zero failures and zero errors. Test and skip counts are recorded.

## Formal runtime certification

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
runtime SHA256SUMS        = PASS
operator SHA256SUMS       = PASS
ZIP and sidecar           = PASS
preflight/postflight Git  = same clean commit
```

## Current isolated evidence

- prior reconciliation/runtime/package/target evidence: 68 passed;
- quality-gate implementation tests: 9 passed;
- cumulative focused evidence: 77 passed;
- exact published quality-gate blobs match the isolated test inputs;
- quality-gate subset: 9/9 passed;
- compileall for the new quality files: PASS;
- Python lines over 100 characters in the new files: 0;
- quality wrapper `--help`: PASS;
- Ruff formal run: pending;
- mypy formal run: pending;
- combined 77-test run: pending;
- repository-wide pytest: pending;
- real HierarchicalForecast 1.5.1 runtime: pending.

## GitHub Actions

Issue #61 tracks the zero-step runner-start blocker. A run with `steps=null`, no logs, and no
artifacts is not code-validation evidence. Close the issue only after checkout, dependency setup,
Ruff, compileall, and pytest produce real passing logs.

## Promotion decision

The PR must remain Draft until all of the following exist for the same reviewed head:

1. formal quality-gate exit 0 with exact 77 focused tests and passing full pytest;
2. formal target certification exit 0 with real version 1.5.1 and 40/40 cases;
3. verified runtime, operator, quality, ZIP, and sidecar SHA-256 evidence;
4. GitHub Actions with real passing steps and logs;
5. updated verification report containing all Run IDs and hashes.

No Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective improvement is claimed by these runtime and
quality controls.