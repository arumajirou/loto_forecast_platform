# HierarchicalForecast test plan

## Objective

Verify the reconciliation adapter, 40-case runtime-certification harness, immutable evidence
package, target-machine operator, operational commands, and promotion gates introduced by PR #48.

## Test strategy

Testing is split into focused layers so failures can be classified before running expensive
repository-wide validation.

1. adapter contract tests
2. all-method state-matrix tests
3. runtime-certification tests
4. console-entry tests
5. immutable package tests
6. target-machine operator tests
7. target-machine real-package certification
8. repository static checks and full pytest
9. GitHub Actions verification

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

## Target-machine operator tests

Targets:

```text
scripts/run_hierarchicalforecast_target_certification.py
tests/test_reconciliation_target_machine_certification.py
```

Required coverage:

- a complete synthetic 40-case runtime and ZIP bundle passes independent verification
- an incorrect summary count fails closed
- a mismatched ZIP sidecar fails closed
- removed `actual_execution=true` evidence is detected even after runtime hashes are recomputed
- unsafe checksum traversal is rejected
- successful orchestration publishes operator report, command logs, manifest, and SHA256SUMS
- exact-version mismatch returns non-success while retaining operator evidence
- a dirty Git worktree fails preflight

Current isolated evidence: 8 passed.

The target-machine operator additionally requires, during real execution:

- clean Git state and optional exact expected head SHA
- `uv sync --extra full --locked`
- exact installed version `1.5.1`
- `uv run --locked` for version query and formal command
- independent verification of all 40 rows
- exactly 24 executed and 16 rejected cases
- runtime artifact and ZIP re-verification

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
  tests/test_reconciliation_package_certification.py \
  tests/test_reconciliation_target_machine_certification.py
```

Current unique focused evidence across separate isolated runs: 61 passed.

The value 61 must not be described as one repository invocation unless the combined command is
actually executed and recorded.

## Target-machine real-package test

From a clean checkout of the intended branch head:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_target_certification.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

The operator internally executes locked synchronization, exact-version verification, and the
registered formal certifier. It then independently verifies runtime files, all 40 case rows, the
24/16 execution partition, ZIP members and metadata, canonical package manifest, sidecar, and
content hashes.

Required result:

```text
exit_code                       = 0
operator_status                  = VERIFIED
operator_formal_success          = true
installed_version                = 1.5.1
summary.expected_cases           = 40
summary.executed_cases           = 40
summary.passed_cases             = 40
summary.failed_cases             = 0
method_partition.executed_cases  = 24
method_partition.rejected_cases  = 16
```

Retain both evidence roots:

```text
artifacts/hierarchicalforecast-runtime/<run-id>/
artifacts/hierarchicalforecast-runtime/<run-id>.zip
artifacts/hierarchicalforecast-runtime/<run-id>.zip.sha256

artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
```

Verify the operator evidence with:

```bash
(
  cd artifacts/hierarchicalforecast-target-runs/<operator-run-id>
  sha256sum -c SHA256SUMS
)
```

Retain Run IDs, ZIP SHA-256, Git commit, exact package version, summary counts, method partition,
command logs, and checksum verification output.

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

Issue #61 tracks the current zero-step runner-start blocker. The latest inspected target-runner
head produced run #1138 with `steps=null` and no logs. A repeated zero-step run is not new
code-validation evidence.

## Promotion decision table

| Evidence | Required before ready for review |
|---|---|
| 61 focused tests | yes; currently available across separate runs |
| real 1.5.1 40-case success | yes; pending |
| runtime and operator SHA verification | yes; pending real run |
| Ruff | yes; pending |
| mypy where required | yes; pending |
| full pytest | yes; pending |
| GitHub Actions real-step success | yes; blocked by #61 |
| Hit@±1 and forecasting metrics | no; outside component scope |

## Regression policy

Any future code change to the adapter, runtime harness, package layer, target-machine operator,
entry point, or artifact schema requires rerunning the affected focused tests. Changes to
dependencies, workflow, or packaging require a new target-machine certification Run ID. Raw
evidence from prior runs must not be overwritten.
