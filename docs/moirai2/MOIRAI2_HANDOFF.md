# Moirai 2.0 Handoff

PR #83 is the P0-P6 base, PR #86 is P7, PR #87 is the P8 certifier, PR #89 is the P8A campaign,
and P8B continues only on `feat/moirai2-lock-review-v1`. Do not retarget or write to any parent
branch.

## 1. Generate a candidate without changing the lane

Use a new output directory. The candidate command copies the lane declaration and resolves a lock
inside the artifact directory only.

```bash
uv run python scripts/generate_moirai2_lock_candidate.py \
  --runtime-lane supported-py311 \
  --python 3.11 \
  --output-dir artifacts/moirai2/lock-candidate/<RUN_ID>
```

Inspect all of the following before approval:

```text
CANDIDATE_RESULT.json
LOCK_REVIEW_REPORT.json
LOCK_DEPENDENCY_INVENTORY.csv
candidate-project/pyproject.toml
candidate-project/uv.lock
ARTIFACT_MANIFEST.json
SHA256SUMS
stdout.log
stderr.log
exit_code.txt
```

`CANDIDATE_RESULT.status=PASS` means only that resolution and automated static review passed. It is
not human approval, frozen synchronization, runtime certification, or model success.

## 2. Dry-run the reviewed installation

Copy the exact `candidate_lock_sha256` from `CANDIDATE_RESULT.json`. Supply a real reviewer identity
and timezone-aware review time.

```bash
uv run python scripts/install_reviewed_moirai2_lock.py \
  --candidate-dir artifacts/moirai2/lock-candidate/<RUN_ID> \
  --output-dir artifacts/moirai2/lock-install-plan/<DRY_RUN_ID> \
  --runtime-lane supported-py311 \
  --reviewer "<REVIEWER>" \
  --reviewed-at "2026-08-06T00:00:00+09:00" \
  --expected-lock-sha256 "<LOCK_SHA256>" \
  --approval-token APPLY-REVIEWED-MOIRAI2-LOCK
```

Without `--apply`, this validates the candidate and prints the installation plan without modifying
the runtime lane.

## 3. Apply only after review

```bash
uv run python scripts/install_reviewed_moirai2_lock.py \
  --candidate-dir artifacts/moirai2/lock-candidate/<RUN_ID> \
  --output-dir artifacts/moirai2/lock-install/<APPLY_RUN_ID> \
  --runtime-lane supported-py311 \
  --reviewer "<REVIEWER>" \
  --reviewed-at "2026-08-06T00:00:00+09:00" \
  --expected-lock-sha256 "<LOCK_SHA256>" \
  --approval-token APPLY-REVIEWED-MOIRAI2-LOCK \
  --apply
```

The lane receives `uv.lock`, `LOCK_REVIEW_REPORT.json`, and `LOCK_REVIEW_APPROVAL.json`. If any
reviewed-lock artifacts already exist, installation fails unless `--replace-existing-sha256`
matches the currently installed lock. Existing artifacts are backed up into the new installation evidence directory
before replacement. The candidate directory remains unchanged.

## 4. Run P8A only after the three-artifact gate passes

```bash
uv run python scripts/preflight_moirai2_runtime_lane.py \
  --runtime-lane supported-py311 \
  --device cpu \
  --snapshot-path /absolute/path/to/pinned/snapshot \
  --output-dir artifacts/moirai2/preflight/<RUN_ID>
```

Then run the full six-case campaign. Repeat for CUDA only after the supported CPU lane is understood.
Never reuse output directories. Preserve candidate, approval, preflight, campaign, per-case, GPU,
log, manifest, and SHA evidence.

Do not open OOF, Holdout, or Prospective work until all six real cases pass and
`formal_runtime_certified=true`. Keep all stacked PRs Draft until real execution, Ruff, mypy,
focused tests, one final full pytest, and one actionable CI run pass.
