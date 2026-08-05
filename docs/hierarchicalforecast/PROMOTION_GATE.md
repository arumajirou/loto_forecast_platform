# HierarchicalForecast sealed local promotion gate

## Status

`IMPLEMENTED / HARDENED_ISOLATED_TESTS_PASS / LOCK_PREFLIGHT_ENFORCED / FORMAL_EXECUTION_PENDING`

The promotion gate runs all local promotion requirements on one clean Git commit. It never marks
the pull request ready, requests review, enables auto-merge, or merges. GitHub Actions with real
passing steps remains a separate mandatory gate.

## Formal command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

`--expected-git-sha` is mandatory.

## Dependency preflight

Before the promotion module creates a promotion Run ID, its formal wrapper parses
`pyproject.toml` and `uv.lock` with the standard-library `tomllib` module.

It requires:

```text
project Python range includes 3.13
lock Python range includes 3.13
dev extra contains pytest, pytest-cov, Ruff, mypy, and Pydantic
full extra contains exactly one HierarchicalForecast declaration
uv.lock resolves only hierarchicalforecast==1.5.1
the root lock package retains HierarchicalForecast in the full extra
```

The declaration may remain broader than the formal version, but the locked resolution may not.
A mismatch returns:

```text
status = FAILED_DEPENDENCY_CONTRACT_PREFLIGHT
exit   = 3
```

The quality child validates the same contract again, records both source-file SHA-256 values in
`QUALITY_REPORT.json`, and target certification independently verifies the installed version.

## Fixed order

```text
1. locked dependency-contract preflight
2. clean expected Git preflight
3. formal quality gate
4. independent quality report, manifest, and SHA256SUMS verification
5. formal target certification
6. independent operator report, manifest, and SHA256SUMS verification
7. standalone verification of the produced ZIP and sidecar
8. Run ID, ZIP path, and ZIP SHA-256 cross-check
9. unchanged clean Git postflight
10. promotion report, manifest, and SHA256SUMS sealing
```

A failed stage prevents every later stage from running.

## Independent child-evidence checks

The promotion gate does not accept a child gate solely because it printed `VERIFIED`. It requires:

- child `expected_git_sha`, `git_commit`, preflight commit, and postflight commit to equal the
  promotion commit;
- clean child preflight and postflight worktrees;
- exact quality JUnit totals: `tests=95`, `failures=0`, `errors=0`;
- full-suite JUnit with zero failures and errors;
- target installed version exactly `1.5.1`;
- target summary `expected=40`, `executed=40`, `passed=40`, `failed=0`;
- target method partition `executed_cases=24`, `rejected_cases=16`;
- canonical persisted child reports and artifact manifests;
- manifest Run ID equal to the evidence-directory name;
- exact manifest and `SHA256SUMS` coverage with no duplicate or unsafe names;
- no symbolic-link path components in child evidence or runtime ZIP paths;
- standalone verifier Run ID, ZIP path, and ZIP SHA-256 equal to target evidence.

## Success boundary

```text
status           = LOCAL_GATES_VERIFIED
formal_success   = true
ready_for_review = false
ci_required      = true
exit             = 0
```

Local success is not a review-readiness or merge verdict.

## Evidence root

```text
artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>/
├── quality.stdout.log
├── quality.stderr.log
├── target.stdout.log
├── target.stderr.log
├── package_verification.stdout.log
├── package_verification.stderr.log
├── COMMANDS.json
├── PROMOTION_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

The promotion root links but does not replace the independent runtime, operator, and quality roots.

## Isolated evidence

```text
hardened promotion tests = 11/11 PASS
quality-gate tests       = 9/9 PASS
lock 1.5.1               = accepted
lock 1.5.0 mutation      = rejected
compileall               = PASS
Python lines over 100    = 0
focused contract         = 95 tests
```

The exact current branch still requires the formal promotion command, Ruff, mypy, one combined
95-test run, full pytest, real HierarchicalForecast 1.5.1 execution, `/mnt/e` publication, and
GitHub Actions with real steps.

## Safety boundary

Even after a local zero exit:

- `ready_for_review` remains false;
- issue #61 remains open until usable CI exists;
- no pull-request state transition occurs;
- no Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective claim is created.
