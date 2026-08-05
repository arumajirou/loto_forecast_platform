# HierarchicalForecast sealed local promotion gate

## Status

`IMPLEMENTED / HARDENED_ISOLATED_TESTS_PASS / FORMAL_EXECUTION_PENDING`

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

## Fixed order

```text
1. clean expected Git preflight
2. formal quality gate
3. independent quality report, manifest, and SHA256SUMS verification
4. formal target certification
5. independent operator report, manifest, and SHA256SUMS verification
6. standalone verification of the produced ZIP and sidecar
7. Run ID, ZIP path, and ZIP SHA-256 cross-check
8. unchanged clean Git postflight
9. promotion report, manifest, and SHA256SUMS sealing
```

A failed stage prevents every later stage from running.

## Independent child-evidence checks

The promotion gate does not accept a child gate solely because it printed `VERIFIED`. It
independently requires:

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

## Failure statuses

```text
FAILED_PREFLIGHT
FAILED_QUALITY_GATE
FAILED_TARGET_CERTIFICATION
FAILED_PACKAGE_VERIFICATION
FAILED_POSTFLIGHT_GIT_DRIFT
FAILED_PROMOTION_GATE
FAILED_PROMOTION_BOOTSTRAP
```

Exit `2` is a local gate or evidence-verification failure after evidence creation. Exit `3` is a
bootstrap, preflight, path-integrity, or postflight failure.

## Isolated evidence

```text
hardened promotion tests = 11/11 PASS
new rejection checks     = child Git mismatch, focused-count mismatch, version mismatch
operator Git field       = explicitly persisted and tested
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
