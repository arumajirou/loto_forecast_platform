# Merlion isolated lock admission

A generated isolated `uv.lock` is not admitted merely because bootstrap completed.

Formal admission requires all of the following:

1. the bootstrap evidence ZIP verifies and reports `BOOTSTRAP_PASS`;
2. the workspace lock equals the ZIP-embedded lock byte for byte;
3. the embedded dependency audit reports `PASS` and binds the same lock SHA-256;
4. Git HEAD equals the expected reviewed implementation commit;
5. the only Git change is `environments/merlion-core-py311/uv.lock`;
6. every registry package has an explicit license expression, evidence reference, and
   `APPROVED` decision;
7. the license review is bound to both the evidence ZIP and lock SHA-256.

The admission command writes JSON and Markdown decisions but never commits the lock. A human must
review the decision and create a separate intentional lock-only commit.

## Create the license review template

```bash
PYTHONPATH="$PWD/src" python3 scripts/create_merlion_license_review_template.py \
  --evidence-zip artifacts/merlion-bootstrap-packages/<RUN_ID>.zip \
  --output artifacts/merlion-lock-admission/<RUN_ID>/LICENSE_REVIEW_TEMPLATE.json
```

Complete the reviewer, review time, license expression, evidence, and decision for every package.
Then finalize the review without changing the human decisions:

```bash
PYTHONPATH="$PWD/src" python3 scripts/finalize_merlion_license_review.py \
  --template artifacts/merlion-lock-admission/<RUN_ID>/LICENSE_REVIEW_TEMPLATE.json \
  --output artifacts/merlion-lock-admission/<RUN_ID>/LICENSE_REVIEW.json
```

The finalizer rejects pending decisions and missing evidence, derives the overall decision, and
adds the canonical `review_sha256`. It does not approve a package automatically.

## Run admission

```bash
HEAD_SHA="$(git rev-parse HEAD)"
PYTHONPATH="$PWD/src" python3 scripts/admit_merlion_core_lock.py \
  --root "$PWD" \
  --evidence-zip artifacts/merlion-bootstrap-packages/<RUN_ID>.zip \
  --license-review artifacts/merlion-lock-admission/<RUN_ID>/LICENSE_REVIEW.json \
  --expected-head "$HEAD_SHA" \
  --report artifacts/merlion-lock-admission/<RUN_ID>/LOCK_ADMISSION_REPORT.json \
  --decision artifacts/merlion-lock-admission/<RUN_ID>/LOCK_ADMISSION_DECISION.md
```

Only `LOCK_ADMISSION_STATUS=ADMITTED` permits the separate lock-only commit step. Admission does
not prove that the resulting commit preserved the exact lock. After committing, continue with
`docs/merlion/LOCK_COMMIT_CERTIFICATION.md` and require `LOCK_COMMIT_CERTIFIED` before runtime.
