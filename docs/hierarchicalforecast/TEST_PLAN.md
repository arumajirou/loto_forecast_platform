# HierarchicalForecast test plan

## Objective

Verify the reconciliation adapter, 40-case runtime-certification harness, immutable evidence
package, operational command, and promotion gates introduced by PR #48.

## Test strategy

Testing is split into focused layers so failures can be classified before running expensive
repository-wide validation.

1. adapter contract tests
2. all-method state-matrix tests
3. runtime-certification tests
4. console-entry tests
5. immutable package tests
6. target-machine real-package certification
7. repository static checks and full pytest
8. GitHub Actions verification

Focused tests must run before repository-wide tests. A passing test double does not replace the
real installed `hierarchicalforecast==1.5.1` certification.

## Adapter contract tests

Target:

```text
tests/test_reconciliation.py
```

Required coverage:

- real `fit_predict()` path is invoked
- constructor-only availability is not accepted as success
- safe defaults are selected per method
- explicit method options are preserved
- accepted upstream arguments are signature-filtered
- sparse methods receive CSR
- paired in-sample arrays are required when declared
- output dictionary `mean` is normalized
- expected shape is enforced
- NaN and infinity are rejected
- incoherent output is rejected
- verified output is coherent and finite
- upstream execution exceptions fail closed

Current isolated evidence: 19 passed.

## Ten-class state-matrix tests

Target:

```text
tests/test_reconciliation_upstream_matrix.py
```

Required coverage:

- all ten registered class names are partitioned exactly once
- executable classes use actual execution
- sparse variants use CSR
- strict-tree classes reject the grouped hierarchy before construction
- ERM receives paired actual and fitted arrays
- method options and expected statuses remain explicit

Current isolated evidence: 12 passed.

## Runtime-certification tests

Target:

```text
tests/test_reconciliation_runtime_certification.py
```

Required coverage:

- formal default generates 4 games × 10 methods = 40 cases
- dependency missing creates complete blocked evidence
- exact-version mismatch fails closed
- module/distribution inconsistency fails closed
- incoherent case fails formal success
- one method exception is recorded and remaining cases continue
- generated inputs are deterministic
- digit games and duplicates are rejected
- CLI exit code matches formal status
- required runtime artifacts and portable SHA256SUMS are written

Current isolated evidence: 9 passed.

## Console-entry tests

Target:

```text
tests/test_reconciliation_console_script.py
```

Required coverage:

- `pyproject.toml` registers `loto-hierarchicalforecast-certify`
- entry point resolves to `loto.reconciliation.package_certification:main`
- resolved target is callable

Current isolated evidence: 2 passed.

## Immutable-package tests

Target:

```text
tests/test_reconciliation_package_certification.py
```

Required coverage:

- valid runtime evidence produces ZIP and sidecar
- fixed ZIP metadata is enforced
- unchanged evidence produces identical package bytes
- an identical existing ZIP is reused without replacement
- a differing existing ZIP is rejected without overwrite
- a differing sidecar is rejected without overwrite
- temporary ZIP is verified before publication
- corrupted source artifact is rejected
- unsafe checksum path and path traversal are rejected
- blocked formal certification is packaged but returns exit 2
- configuration, harness, and packaging failures return structured exit 3
- package failure preserves Run ID and run-directory context

Current isolated evidence: 11 passed.

## Static checks

Run after focused implementation tests:

```bash
python -m ruff format --check src scripts tests
python -m ruff check src scripts tests
python -m compileall -q src scripts tests
```

Run mypy for the repository's supported typed scope when available. Record exact commands and
results rather than claiming an unavailable check.

Current evidence:

- compileall: PASS
- manual Python line-length inspection, maximum 100: PASS
- simple secret-pattern scan: PASS
- Ruff: NOT_RUN in the isolated environment
- mypy: NOT_RUN in the isolated environment

## Focused test command

On a prepared repository environment:

```bash
python -m pytest -q \
  tests/test_reconciliation.py \
  tests/test_reconciliation_upstream_matrix.py \
  tests/test_reconciliation_runtime_certification.py \
  tests/test_reconciliation_console_script.py \
  tests/test_reconciliation_package_certification.py
```

Current unique focused evidence across separate isolated runs: 53 passed.

The value 53 must not be described as one repository invocation unless the combined command is
actually executed and recorded.

## Target-machine real-package test

Precondition:

```bash
uv sync --extra full
uv run python - <<'PY'
from importlib.metadata import version
assert version("hierarchicalforecast") == "1.5.1"
print(version("hierarchicalforecast"))
PY
```

Formal execution:

```bash
uv run loto-hierarchicalforecast-certify
```

Required result:

```text
exit_code      = 0
status         = VERIFIED
expected_cases = 40
executed_cases = 40
passed_cases   = 40
failed_cases   = 0
```

Integrity verification:

```bash
cd artifacts/hierarchicalforecast-runtime
sha256sum -c <run-id>.zip.sha256
unzip -t <run-id>.zip
cd <run-id>
sha256sum -c SHA256SUMS
```

Retain Run ID, ZIP SHA-256, Git commit, exact package version, summary counts, and command logs.

## Repository-wide tests

Run only after focused and real-package validation are understood:

```bash
python -m pytest -q
```

A failure must be classified as:

- introduced by PR #48
- pre-existing repository failure
- dependency/environment failure
- resource or timeout failure

Do not hide failures by selecting only the passing subset.

## GitHub Actions verification

Workflow:

```text
.github/workflows/ci.yml
```

Required evidence:

- runner starts
- checkout step log exists
- dependency-install log exists
- Ruff results exist
- compileall result exists
- pytest result exists
- required check concludes successfully

Issue #61 tracks the current zero-step runner-start blocker. A rerun with no steps, no logs, and no
artifacts is not new code-validation evidence.

## Promotion decision table

| Evidence | Required before ready for review |
|---|---|
| 53 focused tests | yes; currently available |
| real 1.5.1 40-case success | yes; pending |
| ZIP and SHA verification | yes; pending real run |
| Ruff | yes; pending |
| mypy where required | yes; pending |
| full pytest | yes; pending |
| GitHub Actions real-step success | yes; blocked by #61 |
| Hit@±1 and forecasting metrics | no; outside component scope |

## Regression policy

Any future code change to the adapter, runtime harness, package layer, entry point, or artifact
schema requires rerunning the affected focused tests. Changes to dependencies, workflow, or
packaging require a new target-machine certification Run ID. Raw evidence from prior runs must not
be overwritten.
