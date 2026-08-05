# HierarchicalForecast local quality gate

## Status

`IMPLEMENTED / ISOLATED_QUALITY_AND_PROMOTION_TESTS_PASS / FORMAL_92_AND_FULL_SUITE_PENDING`

The quality gate runs the remaining local code-quality checks in a fixed order and preserves
command, JUnit, Git, and checksum evidence. The sealed promotion gate subsequently consumes and
re-verifies this evidence before starting real runtime certification.

## Formal commands

Run the quality gate directly:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_quality_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Or run the complete local sequence:

```bash
python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Both commands require the expected Git SHA. Production does not expose phase bypasses.

## Execution order

```text
1. clean expected Git commit preflight
2. uv sync --extra dev --extra full --locked
3. uv pip check
4. Ruff format check over src, scripts, tests
5. Ruff lint over src, scripts, tests
6. compileall over src, scripts, tests
7. mypy over reconciliation and target modules
8. focused pytest with JUnit XML
9. repository-wide pytest with JUnit XML
10. unchanged clean Git commit postflight
11. immutable quality manifest and SHA256SUMS
```

The repository-wide pytest step runs only after every lighter check and the focused suite pass.

## Focused-suite contract

```text
tests/test_reconciliation.py
tests/test_reconciliation_upstream_matrix.py
tests/test_reconciliation_runtime_certification.py
tests/test_reconciliation_console_script.py
tests/test_reconciliation_package_certification.py
tests/test_reconciliation_package_verifier.py
tests/test_reconciliation_target_machine_certification.py
tests/test_reconciliation_target_operator.py
tests/test_reconciliation_promotion_gate.py
tests/test_reconciliation_quality_gate.py
```

Formal acceptance requires:

```text
tests    = 92
failures = 0
errors   = 0
```

The standalone package verifier contributes seven tests. The sealed promotion gate contributes
eight tests. Console registration for both package commands remains covered by the existing two
console tests.

## mypy scope

```text
src/loto/reconciliation/hierarchy.py
src/loto/reconciliation/runtime_certification.py
src/loto/reconciliation/package_certification.py
src/loto/reconciliation/portable_package_certification.py
src/loto/reconciliation/package_verifier.py
scripts/hierarchicalforecast_target/
```

The promotion-gate implementation is included through `scripts/hierarchicalforecast_target/`.

## Evidence directory

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
├── sync and dependency logs
├── Ruff, compileall, and mypy logs
├── focused_pytest logs and focused.junit.xml
├── full_pytest logs and full.junit.xml
├── COMMANDS.json
├── QUALITY_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

Failure evidence is retained. A failed command does not erase earlier logs.

## Statuses and exit codes

| Exit | Meaning |
|---:|---|
| 0 | every formal quality step and postflight Git check passed |
| 2 | a quality command or JUnit contract failed after evidence creation |
| 3 | bootstrap, preflight, path, or postflight integrity failed |

Structured statuses include `FAILED_SYNC`, `FAILED_PIP_CHECK`, `FAILED_RUFF_FORMAT`,
`FAILED_RUFF_LINT`, `FAILED_COMPILEALL`, `FAILED_MYPY`, `FAILED_FOCUSED_TESTS`,
`FAILED_FULL_TESTS`, and `FAILED_POSTFLIGHT_GIT_DRIFT`.

## Current evidence boundary

```text
standalone verifier tests = 7/7 PASS
promotion-gate tests      = 8/8 PASS
compileall                = PASS
Python lines over 100     = 0
promotion wrapper --help  = PASS
remote/local blob equality = PASS
```

The branch now has 92 cumulative focused tests across separate isolated runs. A single formal
92-test invocation, formal Ruff, formal mypy, and repository-wide pytest remain pending on the
target machine. Neither the quality gate nor the promotion gate replaces real
HierarchicalForecast 1.5.1 execution or GitHub Actions evidence.
