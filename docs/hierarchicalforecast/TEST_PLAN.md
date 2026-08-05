# HierarchicalForecast test plan

## Objective

Verify the reconciliation adapter, deterministic 40-case runtime harness, immutable runtime
package, standalone transferred-package verifier, hardened target-machine operator, sealed local
quality gate, and sealed local promotion gate introduced by PR #48.

A test double never replaces real installed `hierarchicalforecast==1.5.1` execution.

## Required order

Run the least expensive and most diagnostic checks first:

1. adapter contract;
2. all-ten-method state matrix;
3. runtime certification;
4. console entry points;
5. immutable and portable runtime package;
6. standalone transferred-package verification;
7. hardened target runtime/package verification;
8. hardened target operator control;
9. sealed local promotion-gate tests;
10. sealed local quality-gate tests;
11. formal local promotion gate, which runs quality, runtime, and package verification;
12. GitHub Actions verification.

The repository-wide pytest step must remain last inside the quality-gate stage.

## Focused test contract

| File | Scope | Current isolated evidence |
|---|---|---:|
| `tests/test_reconciliation.py` | adapter execution and validation | 19 passed |
| `tests/test_reconciliation_upstream_matrix.py` | all ten methods and state partition | 12 passed |
| `tests/test_reconciliation_runtime_certification.py` | 40-case orchestration and artifacts | 9 passed |
| `tests/test_reconciliation_console_script.py` | certification and verification entry points | 2 passed |
| `tests/test_reconciliation_package_certification.py` | immutable/portable ZIP publication | 11 passed |
| `tests/test_reconciliation_package_verifier.py` | transferred ZIP and sidecar verification | 7 passed |
| `tests/test_reconciliation_target_machine_certification.py` | runtime/package/source verification | 9 passed |
| `tests/test_reconciliation_target_operator.py` | target operator and Git controls | 6 passed |
| `tests/test_reconciliation_promotion_gate.py` | chained local gates and evidence integrity | 8 passed |
| `tests/test_reconciliation_quality_gate.py` | quality ordering, JUnit, failure and Git controls | 9 passed |
| **Total** | separate isolated runs | **92 passed** |

The value 92 is cumulative evidence across separate isolated runs. It is not yet one combined
pytest invocation.

## Formal local promotion gate

Run from a clean checkout of the exact PR head:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

The runner performs:

```text
clean Git preflight
formal quality gate
quality SHA256SUMS and artifact-manifest verification
formal target certification with real hierarchicalforecast==1.5.1
operator SHA256SUMS and artifact-manifest verification
standalone ZIP and sidecar verification
Run ID, ZIP path, and ZIP SHA-256 cross-stage comparison
clean unchanged Git postflight
promotion evidence sealing
```

A stage failure prevents all later stages from running.

Successful local output must be:

```text
status           = LOCAL_GATES_VERIFIED
formal_success   = true
ready_for_review = false
ci_required      = true
exit             = 0
```

## Formal quality contract

The quality stage performs:

```text
uv sync --extra dev --extra full --locked
uv pip check
Ruff format --check
Ruff check
compileall
mypy on reconciliation, package verifier, and target scope
focused pytest with JUnit XML
repository-wide pytest with JUnit XML
postflight Git verification
SHA-256 evidence sealing
```

Focused JUnit acceptance is exact:

```text
tests=92, failures=0, errors=0
```

The full-suite JUnit must report zero failures and zero errors. Test and skip counts are recorded.

## Formal runtime contract

The target stage must produce:

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

The resulting ZIP must pass the standalone verifier and match the target report's Run ID, path,
and SHA-256.

## Current isolated evidence

- focused evidence before the promotion gate: 84 passed;
- sealed promotion-gate tests: 8 passed;
- cumulative focused evidence: 92 passed;
- promotion implementation, wrapper, and test Git blobs match the isolated test inputs;
- promotion test subset: 8/8 passed;
- promotion compileall: PASS;
- Python lines over 100 characters in promotion files: 0;
- promotion wrapper `--help`: PASS;
- Ruff formal run: pending;
- mypy formal run: pending;
- combined 92-test run: pending;
- repository-wide pytest: pending;
- real HierarchicalForecast 1.5.1 runtime: pending;
- real transferred package verification: pending;
- formal promotion-gate run: pending.

## GitHub Actions

Issue #61 tracks the zero-step runner-start blocker. A run with `steps=null`, no logs, and no
artifacts is not code-validation evidence. Close the issue only after checkout, dependency setup,
Ruff, compileall, and pytest produce real passing logs.

## Promotion decision

The PR must remain Draft until all of the following exist for the same reviewed head:

1. formal promotion-gate exit 0 with exact 92 focused tests and passing full pytest;
2. real version 1.5.1 execution with 40/40 cases;
3. standalone verification exit 0 for the resulting ZIP and sidecar;
4. verified runtime, operator, quality, promotion, ZIP, and sidecar SHA-256 evidence;
5. GitHub Actions with real passing steps and logs;
6. updated verification report containing every Run ID and hash.

A zero local-promotion exit does not change the pull-request state. No Hit@±1, MAE, MSE, RMSE,
Holdout, or Prospective improvement is claimed by these runtime and quality controls.
