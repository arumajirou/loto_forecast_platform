# P8B Test Plan

## Pure review tests

1. Parse exact project dependencies.
2. Inspect a registry-only lock and retain package/edge/hash inventory.
3. Reject Git, path, and editable package sources.
4. Reject registry packages without valid SHA-256 artifacts.
5. Reject direct dependency version mismatches.
6. Reject unresolved dependency names.
7. Retain multiple locked versions as a warning.
8. Reject approval of a failed report.
9. Require reviewer identity and timezone-aware review time.
10. Cross-check project, lock, report, approval, inventory, and lane identity.

## Workflow tests

1. Candidate generation writes only to a new output directory.
2. Candidate generation does not create or modify the lane lock.
3. Failed static review remains preserved as failed evidence.
4. Installer dry-run leaves the lane and candidate artifact unchanged.
5. Installer rejects an incorrect candidate lock SHA.
6. Installer rejects an incorrect approval token.
7. Installer writes three cross-hashed lane artifacts and separate installation evidence on apply.
8. Installer requires the current lock SHA before replacement.
9. Runtime preflight rejects missing approval and tampered lock evidence.
10. CPU frozen probe isolation and unavailable-CUDA rejection remain covered.

## Static checks

- focused pytest;
- compileall;
- JSON and CSV parsing;
- Python line-length check;
- P8B delta manifest verification;
- cumulative manifest cross-check;
- secret-pattern scan;
- principal Git blob identity verification.

## Deferred target-host checks

- actual `uv lock` for both lanes;
- dependency graph and license review by a human;
- lock installation into the target-host lane;
- `uv run --frozen` synchronization and import probe;
- CPU and CUDA P8A campaigns;
- Ruff, mypy, and final full pytest.
