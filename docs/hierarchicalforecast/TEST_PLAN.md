# HierarchicalForecast test plan

## Objective

Verify the reconciliation adapter, deterministic 40-case runtime harness, immutable package,
hardened target-machine operator, and promotion gates introduced by PR #48.

## Test order

Run the least expensive and most diagnostic scopes first:

1. adapter contract;
2. all-ten-method state matrix;
3. runtime certification;
4. console entry point;
5. immutable runtime package;
6. hardened target runtime/package verification;
7. hardened target operator control;
8. real installed-package target certification;
9. Ruff, supported mypy scope, and combined focused tests;
10. repository-wide pytest;
11. GitHub Actions verification.

A passing test double never replaces real installed `hierarchicalforecast==1.5.1` execution.

## Existing focused groups

| File | Scope | Current isolated evidence |
|---|---|---:|
| `tests/test_reconciliation.py` | adapter execution, validation, failure states | 19 passed |
| `tests/test_reconciliation_upstream_matrix.py` | all ten methods and expected partition | 12 passed |
| `tests/test_reconciliation_runtime_certification.py` | 40-case orchestration and artifacts | 9 passed |
| `tests/test_reconciliation_console_script.py` | registered entry point | 2 passed |
| `tests/test_reconciliation_package_certification.py` | immutable package and tamper rejection | 11 passed |

Subtotal: 53 passed across separate isolated runs.

## Hardened target verification tests

Target:

```text
tests/test_reconciliation_target_machine_certification.py
```

Required coverage:

- complete sealed 40-case bundle accepted;
- aggregate case-count drift rejected;
- ZIP sidecar drift rejected;
- missing actual-execution evidence rejected;
- output-shape evidence drift rejected;
- duplicate runtime artifact-manifest row rejected;
- symbolic-link runtime artifact rejected;
- checksum traversal rejected;
- runtime-recorded source SHA-256 recomputed and drift rejected.

Current isolated evidence: 9 passed.

## Hardened target operator tests

Target:

```text
tests/test_reconciliation_target_operator.py
```

Required coverage:

- full synthetic operator success with separate evidence directory;
- version mismatch returns non-success and retains evidence;
- dirty preflight fails;
- postflight Git commit or worktree drift fails;
- sync bypass is rejected outside isolated test mode;
- expected Git SHA is required outside isolated test mode.

Current isolated evidence: 6 passed.

Synthetic fixture support is isolated in:

```text
tests/hierarchicalforecast_target_fixtures.py
```

## Hardened target module tests

Implementation under test:

```text
scripts/run_hierarchicalforecast_target_certification.py
scripts/hierarchicalforecast_target/
├── constants.py
├── integrity.py
├── runtime_verification.py
├── package_verification.py
└── operator.py
```

The test design must preserve the following boundaries:

- the production CLI requires `--expected-git-sha`;
- synchronization cannot be skipped in production;
- test injection is explicit through `test_mode=True`;
- runtime and operator evidence use different Run IDs;
- runtime files, ZIP, sidecar, and operator files reject symlinks;
- source hashes are recomputed from the checked-out files;
- Git state is checked before and after execution.

## Current focused evidence total

| Test group | Result |
|---|---:|
| Existing reconciliation | 19 passed |
| Ten-class upstream matrix | 12 passed |
| Runtime certification | 9 passed |
| Console entry | 2 passed |
| Immutable package | 11 passed |
| Hardened target verification | 9 passed |
| Hardened target operator | 6 passed |
| **Total** | **68 passed** |

The value 68 is the sum of separate isolated runs. Do not describe it as one combined repository
invocation until that command is actually executed and recorded.

The hardened target subset has been executed together against an exact local reconstruction of the
published Git blobs:

```bash
pytest -q \
  tests/test_reconciliation_target_machine_certification.py \
  tests/test_reconciliation_target_operator.py
```

Observed result:

```text
15 passed
```

## Static checks

After affected focused tests:

```bash
python -m ruff format --check \
  scripts/hierarchicalforecast_target \
  scripts/run_hierarchicalforecast_target_certification.py \
  tests/test_reconciliation_target_machine_certification.py \
  tests/test_reconciliation_target_operator.py \
  tests/hierarchicalforecast_target_fixtures.py

python -m ruff check \
  scripts/hierarchicalforecast_target \
  scripts/run_hierarchicalforecast_target_certification.py \
  tests/test_reconciliation_target_machine_certification.py \
  tests/test_reconciliation_target_operator.py \
  tests/hierarchicalforecast_target_fixtures.py

python -m compileall -q scripts tests
```

Run mypy for the repository's supported typed scope when available.

Current hardened-target evidence:

- compileall: PASS;
- Python lines over 100 characters: 0;
- wrapper `--help`: PASS;
- remote/local Git blob equality for ten files: PASS;
- Ruff: NOT_RUN, unavailable in the isolated environment;
- mypy: NOT_RUN.

## Combined reconciliation focused command

On a prepared environment:

```bash
python -m pytest -q \
  tests/test_reconciliation.py \
  tests/test_reconciliation_upstream_matrix.py \
  tests/test_reconciliation_runtime_certification.py \
  tests/test_reconciliation_console_script.py \
  tests/test_reconciliation_package_certification.py \
  tests/test_reconciliation_target_machine_certification.py \
  tests/test_reconciliation_target_operator.py
```

This combined command remains pending. Preserve and classify any failure rather than excluding it.

## Real target-machine certification

Preconditions:

- exact current PR head checked out;
- clean worktree;
- functional network or already available locked packages;
- `uv` available;
- writable artifact roots.

Formal command:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

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
actual executions          = 24
grouped rejections         = 16
runtime SHA256SUMS         = PASS
operator SHA256SUMS        = PASS
ZIP and sidecar            = PASS
preflight/postflight Git   = same clean commit
```

Retain operator Run ID, runtime Run ID, Git commit, exact package version, ZIP SHA-256, command logs,
and both SHA manifests.

## Repository-wide validation

Run only after focused and real-package findings are understood:

```bash
python -m pytest -q
```

Classify failures as introduced code, pre-existing repository failure, dependency/environment,
resource/timeout, or infrastructure. Do not hide a failure by selecting only passing tests.

## GitHub Actions

Workflow:

```text
.github/workflows/ci.yml
```

Required evidence:

- job contains real steps;
- checkout and dependency logs exist;
- Ruff and compileall execute;
- pytest executes;
- required checks pass.

Issue #61 tracks the current zero-step blocker. A run with `steps=null`, no logs, and no artifacts is
not code-validation evidence. Do not manually rerun repeatedly without an external condition change.

## Promotion decision

| Evidence | Required before ready for review | Current state |
|---|---|---|
| 68 focused-test evidence | yes | available across isolated runs |
| combined focused invocation | yes | pending |
| real 1.5.1 40-case result | yes | pending |
| runtime/operator/ZIP integrity | yes | pending real run |
| Ruff | yes | pending |
| supported mypy scope | yes where applicable | pending |
| repository-wide pytest | yes | pending |
| GitHub Actions real-step success | yes | blocked by #61 |
| forecast accuracy metrics | no | outside this component |

Any code change to adapter, runtime, package, target verification, target operator, or artifact
schema requires rerunning the affected focused tests. Dependency or packaging changes require a new
real certification Run ID. Existing raw evidence must not be overwritten.
