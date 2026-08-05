# HierarchicalForecast local quality gate

## Status

`IMPLEMENTED / ISOLATED_9_TESTS_PASS / FORMAL_77_AND_FULL_SUITE_PENDING`

The quality gate runs the remaining local promotion checks in a fixed order and preserves all
command, JUnit, Git, and checksum evidence. It is separate from the real
`hierarchicalforecast==1.5.1` runtime certification.

## Formal command

Run from a clean checkout of the current PR head:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_quality_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

`--expected-git-sha` is mandatory. The production CLI does not expose synchronization or
full-suite bypasses.

## Execution order

The runner executes the following sequence:

```text
1. clean expected Git commit preflight
2. uv sync --extra dev --extra full --locked
3. uv pip check
4. Ruff format check over src, scripts, tests
5. Ruff lint over src, scripts, tests
6. compileall over src, scripts, tests
7. mypy over the reconciliation and target-operator scope
8. focused pytest with JUnit XML
9. repository-wide pytest with JUnit XML
10. unchanged clean Git commit postflight
11. immutable quality evidence manifest and SHA256SUMS
```

The repository-wide pytest step runs only after every lighter check and the focused suite pass.
This follows the project policy of deferring the heaviest verification until implementation and
focused checks are complete.

## Focused-suite contract

The focused suite contains these files:

```text
tests/test_reconciliation.py
tests/test_reconciliation_upstream_matrix.py
tests/test_reconciliation_runtime_certification.py
tests/test_reconciliation_console_script.py
tests/test_reconciliation_package_certification.py
tests/test_reconciliation_target_machine_certification.py
tests/test_reconciliation_target_operator.py
tests/test_reconciliation_quality_gate.py
```

Formal acceptance requires the JUnit XML to report exactly:

```text
tests    = 77
failures = 0
errors   = 0
```

The exact count is intentional. Adding or removing a focused test requires an explicit contract
update rather than silently changing the promotion evidence.

## mypy scope

```text
src/loto/reconciliation/hierarchy.py
src/loto/reconciliation/runtime_certification.py
src/loto/reconciliation/package_certification.py
scripts/hierarchicalforecast_target/
```

The gate uses the repository's checked-in `[tool.mypy]` configuration.

## Evidence directory

Each invocation creates a unique directory:

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
├── sync.stdout.log / sync.stderr.log
├── pip_check.stdout.log / pip_check.stderr.log
├── ruff_format.stdout.log / ruff_format.stderr.log
├── ruff_lint.stdout.log / ruff_lint.stderr.log
├── compileall.stdout.log / compileall.stderr.log
├── mypy.stdout.log / mypy.stderr.log
├── focused_pytest.stdout.log / focused_pytest.stderr.log
├── focused.junit.xml
├── full_pytest.stdout.log / full_pytest.stderr.log
├── full.junit.xml
├── COMMANDS.json
├── QUALITY_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

Failure evidence is retained. A failed command does not erase earlier logs.

## Statuses

- `VERIFIED`
- `FAILED_PREFLIGHT`
- `FAILED_SYNC`
- `FAILED_PIP_CHECK`
- `FAILED_RUFF_FORMAT`
- `FAILED_RUFF_LINT`
- `FAILED_COMPILEALL`
- `FAILED_MYPY`
- `FAILED_FOCUSED_TESTS`
- `FAILED_FULL_TESTS`
- `FAILED_POSTFLIGHT_GIT_DRIFT`
- `FAILED_QUALITY_BOOTSTRAP`

## Exit codes

| Exit | Meaning |
|---:|---|
| 0 | every formal quality step and postflight Git check passed |
| 2 | a quality command or JUnit contract failed after evidence creation |
| 3 | bootstrap, preflight, path, or postflight integrity failed |

## Current evidence boundary

The quality-gate implementation has nine isolated tests passing. The branch now has 77 cumulative
focused tests across separate isolated runs. A single formal 77-test run, Ruff, mypy, and the
repository-wide pytest remain pending until this command is executed on the target machine.

This runner does not replace the real HierarchicalForecast 1.5.1 runtime certification or GitHub
Actions evidence. All three evidence roots are required before the PR may leave Draft status.
