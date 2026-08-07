# Merlion isolated lock commit certification

## Purpose

`LOCK_ADMISSION_STATUS=ADMITTED` applies to an uncommitted isolated lock. The lock commit
certification gate proves that the next commit preserved that exact admitted lock and changed
nothing else.

## Required properties

The gate requires all of the following:

- the current worktree and index are clean;
- the current commit has exactly one parent;
- that parent equals the admission expected, actual, and evidence HEAD;
- the parent does not contain the isolated lock;
- the commit adds only `environments/merlion-core-py311/uv.lock`;
- the committed Git blob, workspace file, and admission report have the same SHA-256;
- the admission report is self-hash-valid and has status `ADMITTED`;
- the bootstrap evidence ZIP still verifies as `BOOTSTRAP_PASS`;
- the finalized license review still validates against the embedded dependency inventory;
- the evidence ZIP and license review hashes match the admission report.

A merge commit, detached HEAD, dirty worktree, modified lock, unrelated file, wrong parent, or
changed evidence blocks certification.

## Run after committing only the lock

```bash
HEAD_SHA="$(git rev-parse HEAD)"
RUN_ID="<BOOTSTRAP_RUN_ID>"

PYTHONPATH="$PWD/src" \
python3 scripts/certify_merlion_lock_commit.py run \
  --root "$PWD" \
  --admission-report \
    "artifacts/merlion-lock-admission/${RUN_ID}/LOCK_ADMISSION_REPORT.json" \
  --evidence-zip \
    "artifacts/merlion-bootstrap-packages/${RUN_ID}.zip" \
  --license-review \
    "artifacts/merlion-lock-admission/${RUN_ID}/LICENSE_REVIEW.json" \
  --expected-head "$HEAD_SHA" \
  --report \
    "artifacts/merlion-lock-admission/${RUN_ID}/LOCK_COMMIT_REPORT.json" \
  --decision \
    "artifacts/merlion-lock-admission/${RUN_ID}/LOCK_COMMIT_DECISION.md"
```

Formal runtime certification requires this report through `MERLION_LOCK_COMMIT_REPORT` and
revalidates the current HEAD, parent, worktree, lock bytes, and Git blob before dependency sync.
