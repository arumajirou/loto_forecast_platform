# HierarchicalForecast sealed local promotion gate

## Status

`IMPLEMENTED / ISOLATED_PROMOTION_TESTS_PASS / FORMAL_EXECUTION_PENDING`

The promotion gate runs every local promotion requirement on one clean Git commit and seals the
combined result. It does not mark the pull request ready, request review, enable auto-merge, or
merge. A successful GitHub Actions run with real workflow steps remains a separate requirement.

## Formal command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

`--expected-git-sha` is mandatory.

## Fixed execution order

```text
1. clean expected Git commit preflight
2. formal local quality gate
3. verify the quality evidence directory and SHA256SUMS
4. formal target-machine certification
5. verify the operator evidence directory and SHA256SUMS
6. standalone verification of the produced ZIP and sidecar
7. compare runtime Run ID, ZIP path, and ZIP SHA-256 across stages
8. unchanged clean Git commit postflight
9. seal promotion logs, report, manifest, and SHA256SUMS
```

A failed stage prevents every later stage from running.

## Success result

Local success returns:

```text
status           = LOCAL_GATES_VERIFIED
formal_success   = true
ready_for_review = false
ci_required      = true
exit             = 0
```

`LOCAL_GATES_VERIFIED` means only that the local quality, runtime, operator, package, and integrity
requirements succeeded for the same Git commit. It is not a merge or review-readiness verdict.

## Evidence directory

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

The promotion report links, but does not replace, the independent evidence roots:

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip.sha256
```

## Independent checks

The gate verifies that:

- the preflight and postflight Git commit are identical and clean;
- the quality command and persisted `QUALITY_REPORT.json` are byte-equivalent JSON objects;
- the quality `SHA256SUMS` covers every evidence file except itself;
- the quality artifact manifest covers every pre-manifest artifact;
- the target command and persisted `OPERATOR_REPORT.json` are equivalent;
- the operator `SHA256SUMS` and artifact manifest are complete and correct;
- target certification reports a runtime Run ID, ZIP path, and ZIP SHA-256;
- the standalone verifier returns the same Run ID, ZIP path, and ZIP SHA-256;
- the standalone verifier reports `VERIFIED` and `formal_success=true`.

## Failure statuses

Structured statuses include:

```text
FAILED_PREFLIGHT
FAILED_QUALITY_GATE
FAILED_TARGET_CERTIFICATION
FAILED_PACKAGE_VERIFICATION
FAILED_POSTFLIGHT_GIT_DRIFT
FAILED_PROMOTION_GATE
FAILED_PROMOTION_BOOTSTRAP
```

Exit code `2` represents a local gate or evidence-verification failure after evidence creation.
Exit code `3` represents bootstrap, preflight, or postflight integrity failure.

## Current isolated evidence

```text
promotion-gate tests       = 8/8 PASS
compileall                 = PASS
Python lines over 100      = 0
wrapper --help             = PASS
expected Git SHA required  = PASS
remote/local blob equality = PASS
```

The new eight tests cover success, mandatory Git identity, fail-fast quality and target handling,
quality evidence tampering, standalone verifier failure, runtime identity mismatch, and postflight
Git drift.

## Promotion boundary

Even when the command exits zero:

- `ready_for_review` remains false;
- issue #61 must remain open until GitHub Actions has real passing steps and logs;
- no forecast-accuracy claim is created;
- no Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective claim is created;
- no pull-request state change is performed.
