# Runbook

## Preflight

1. Use a clean checkout of the reviewed branch.
2. Review `default_policy.json` and its policy SHA-256.
3. Confirm `chronyc` is installed for live mode.
4. Choose a new evidence directory outside immutable input directories.
5. Do not open Holdout or Prospective actuals.

## Live check

Run the target-host command from `README.md`. Inspect the process exit code and then independently
run `verify_evidence_bundle` against the output directory. A process exit code of zero is not enough
without complete artifact verification.

## Interpretation

- `HEALTHY`: local operational precondition only; external trust is still false.
- `DEGRADED`: investigate warning checks and do not create a Prediction Lock.
- `BLOCKED`: resolve failed checks and collect a fresh stable observation.
- `UNKNOWN`: restore missing/parser/command evidence and rerun; never override to healthy.

## Incident handling

After a clock step, retain the blocked evidence. Do not overwrite it. Correct the host clock source,
wait for a fresh stable window, and issue a new observation/decision ID in a new output directory.

## Rollback

The implementation is add-only and inactive. Before merge, close the Draft PR. After an approved
merge, revert the PR. No database, data, prediction, dependency, or lockfile repair is required.
