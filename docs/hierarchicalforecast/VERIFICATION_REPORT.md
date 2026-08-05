# HierarchicalForecast verification report

## Report status

- Component: HierarchicalForecast reconciliation adapter and runtime certification
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- Base branch: `main`
- Base commit: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Verification state: `PARTIALLY_VERIFIED / CI_BLOCKED_RUNNER_START`
- Formal promotion state: `NOT_READY`

The branch must remain Draft until the real installed
`hierarchicalforecast==1.5.1` matrix and repository CI both produce usable evidence.

## Scope

This report covers:

- actual upstream `fit_predict()` execution through the project adapter
- all ten registered HierarchicalForecast reconciler classes
- grouped-hierarchy compatibility and strict-tree rejection
- shape, finite-value, and coherence validation
- deterministic runtime-certification orchestration
- artifact manifests and SHA-256 verification
- immutable deterministic ZIP packaging and sidecar verification
- target-machine locked provisioning and independent evidence verification
- structured failure statuses and exit codes
- focused tests and static checks performed in the isolated review environment

This report does not cover forecasting accuracy or claim improvement in Hit@±1, MAE, MSE,
RMSE, Holdout, or Prospective performance.

## Formal runtime matrix

The default certification uses seed `1` and four select-family games:

- `mini`
- `loto6`
- `loto7`
- `bingo5`

It evaluates ten upstream classes per game for 40 formal cases.

Expected executable classes:

- `BottomUp`
- `BottomUpSparse`
- `MinTrace`
- `MinTraceSparse`
- `OptimalCombination`
- `ERM`

Expected grouped-hierarchy rejection:

- `TopDown`
- `TopDownSparse`
- `MiddleOut`
- `MiddleOutSparse`

A case is accepted only when its expected status matches. Executable cases must also record real
execution, the imported package version, expected shape, finite values, and coherence within the
configured tolerance.

## Evidence reviewed

### Adapter and runtime contract

`VERIFIED_WITH_TEST_DOUBLES`

- the selected upstream class is constructed with validated options
- `fit_predict()` is called for executable methods
- sparse methods receive a CSR summing matrix
- paired in-sample actual and fitted matrices are required when upstream declares `insample=True`
- output shape and finite values are checked
- coherence is measured rather than assumed
- strict-tree methods are rejected before construction for the grouped number hierarchy
- unexpected method exceptions are retained and do not stop the remaining matrix

### Packaging contract

`VERIFIED`

- required artifact coverage is checked
- `SHA256SUMS` coverage and digests are checked
- artifact-manifest sizes and hashes are checked
- Run ID and certification status are cross-checked
- member names are restricted to one Run ID prefix
- duplicate ZIP members and path traversal are rejected
- canonical package-manifest bytes are checked
- ZIP metadata is fixed for deterministic output
- temporary ZIPs are verified before publication
- identical existing packages are reused without overwrite
- differing existing ZIPs or sidecars are rejected without overwrite
- failed temporary packages are removed

### Target-machine operator contract

`IMPLEMENTED / VERIFIED_WITH_SYNTHETIC_EVIDENCE`

The target-machine runner:

- requires a clean Git worktree and optionally an exact expected head SHA
- provisions with `uv sync --extra full --locked`
- queries the installed package through `uv run --locked`
- executes the registered formal certifier through `uv run --locked`
- independently reopens all runtime JSON artifacts and verifies their checksums
- independently inspects all 40 method/game rows
- requires 24 actual executions and 16 explicit grouped-hierarchy rejections
- independently verifies ZIP paths, sidecar, members, metadata, manifest bytes, sizes, and hashes
- writes separate operator logs, report, manifest, and portable `SHA256SUMS`
- fails closed on dirty Git state, version drift, case evidence drift, or package tampering

The operator runner is not yet evidence that the real installed 1.5.1 package passed. It is the
reviewed mechanism for obtaining and independently validating that missing evidence.

### Focused tests

The focused evidence is the sum of separate isolated runs, not one repository-wide pytest run.

| Test group | Result |
|---|---:|
| Existing reconciliation tests | 19 passed |
| Ten-class upstream-state matrix | 12 passed |
| Runtime-certification tests | 9 passed |
| Console-entry tests | 2 passed |
| Immutable package-certification tests | 11 passed |
| Target-machine operator tests | 8 passed |
| Total unique focused evidence | 61 passed |

The eight target-machine tests cover successful independent verification, bad summary counts,
sidecar drift, removed actual-execution evidence, checksum traversal, successful operator evidence
publication, exact-version mismatch, and dirty-worktree rejection.

### Static checks

- Python compileall: `PASS`
- Python line-length inspection, maximum 100: `PASS`
- simple secret-pattern scan: `PASS`
- remote/local Git blob equality for reviewed files: `PASS`
- local Ruff: `NOT_RUN`, Ruff was not installed or cached
- local mypy: `NOT_RUN`
- repository-wide pytest: `NOT_RUN`

## External contract evidence

The Nixtla `v1.5.1` source contract was reviewed for the methods used by the adapter.

Confirmed source-level expectations include:

- `MinTrace(method="ols")` does not require in-sample arrays
- `fit_predict(S, y_hat, ...)` returns a result containing `mean`
- MinTrace supports grouped hierarchies
- TopDown and MiddleOut require a strict hierarchy
- ERM requires in-sample evidence
- sparse variants declare sparse execution

Source inspection is not a substitute for an installed-package runtime execution.

## GitHub review state

- unresolved inline review threads: `0`
- human approval: `NONE`
- human requested changes: `NONE`
- only external review submission: Sourcery access notification, not a code review
- mergeability reported by GitHub: `true`
- branch divergence at the latest audit: behind `0`

## GitHub Actions state

`BLOCKED_RUNNER_START`

The latest inspected target-runner head produced:

- head: `936c6f57f8a475bfda2e32f512d8690cae620339`
- run: `30987420472` / run #1138
- job: `92245315209`
- conclusion: `failure`
- `steps=null`
- no checkout log
- no dependency-installation log
- no Ruff, compileall, or pytest log

This is not accepted as a code-test failure, but it also does not provide CI verification. Issue
#61 tracks the repository/account runner-start blocker.

## Promotion gates

| Gate | State | Required evidence |
|---|---|---|
| Adapter contract | PASS | Focused contract tests |
| Ten-class partition | PASS | Complete state-matrix tests |
| Runtime orchestration | PASS_WITH_DOUBLES | 40-case deterministic harness tests |
| Immutable evidence package | PASS | ZIP, manifest, sidecar, tamper tests |
| Target-machine operator | PASS_WITH_SYNTHETIC_EVIDENCE | Eight focused operator tests |
| Unresolved review threads | PASS | Zero unresolved threads |
| Real package runtime | PENDING | Installed `hierarchicalforecast==1.5.1`, 40/40 expected cases |
| Console installation | PENDING_TARGET_HOST | Installed entry point executes in locked target environment |
| Repository CI | BLOCKED | Workflow creates steps and required checks pass |
| Forecast accuracy | NOT_APPLICABLE | Separate time-ordered experiment required |

## Formal acceptance procedure

Run on a clean checkout of the intended target commit:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_target_certification.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

The target runner performs locked synchronization, exact-version verification, formal execution,
and independent runtime/ZIP verification. It writes a separate operator evidence directory with
`OPERATOR_REPORT.json`, logs, manifest, and `SHA256SUMS`.

Promotion requires all of the following:

1. operator command exit code is `0`
2. operator status is `VERIFIED` and `formal_success=true`
3. installed distribution version is exactly `1.5.1`
4. expected, executed, and passed cases are all `40`
5. failed cases are `0`
6. 24 executable cases record `actual_execution=true`
7. 16 grouped-hierarchy rejections record `actual_execution=false`
8. exact-version and module/distribution consistency checks are true
9. runtime `SHA256SUMS`, ZIP sidecar, ZIP structure, and package manifest pass independent checks
10. operator `SHA256SUMS` passes
11. repository Ruff and required static checks pass
12. focused and repository-wide pytest pass
13. repository CI starts real steps and required checks pass

Do not overwrite or delete a mismatched ZIP or sidecar to manufacture a passing rerun. Preserve
it as incident evidence and create a new certification Run ID after investigation.

## Final verdict

`NOT_READY_FOR_REVIEW`

The implementation and focused verification are strong enough for target-machine certification,
but formal readiness is blocked by two missing evidence classes:

- real installed HierarchicalForecast 1.5.1 execution across all 40 cases
- functioning repository CI with actual workflow steps and test logs

The PR must remain Draft. No merge, auto-merge, force push, or direct push to `main` is authorized
by this report.
