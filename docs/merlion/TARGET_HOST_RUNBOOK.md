# Merlion core target-host runbook

## Status boundary

Preflight, bootstrap, evidence packaging, lock admission, lock commit certification, and runtime
certification are separate.

- Preflight checks uv, Python 3.11 availability, DNS, disk space, and writable paths.
- Bootstrap creates, audits, and syncs the isolated lock. It is not runtime certification.
- Evidence packaging preserves either `BOOTSTRAP_PASS` or `BOOTSTRAP_BLOCKED` without promotion.
- Lock admission binds successful evidence, the uncommitted lock, Git scope, and license review.
- Lock commit certification proves the next commit added that exact lock and nothing else.
- Formal runtime certification requires the lock commit report and exact clean certified HEAD.

## 1. Run resumable bootstrap

```bash
cd /mnt/e/env/ts/loto_forecast_platform
SESSION=merlion-core-bootstrap \
  bash scripts/start_merlion_core_bootstrap_tmux.sh
```

The runner never uses sudo, changes system Python, or updates shell profiles. When Python 3.11 is
absent and GitHub is reachable, uv installs it under `artifacts/merlion-managed-python/`.

## 2. Inspect the evidence package

```text
artifacts/merlion-bootstrap/<RUN_ID>/PREFLIGHT.json
artifacts/merlion-bootstrap/<RUN_ID>/BOOTSTRAP_PLAN.json
artifacts/merlion-bootstrap/<RUN_ID>/DEPENDENCY_AUDIT.json
artifacts/merlion-bootstrap/<RUN_ID>/DEPENDENCY_INVENTORY.csv
artifacts/merlion-bootstrap-packages/<RUN_ID>.zip
artifacts/merlion-bootstrap-packages/<RUN_ID>.zip.sha256
artifacts/merlion-bootstrap-packages/<RUN_ID>.verification.json
```

A blocked Run remains blocked even when its evidence ZIP verifies successfully.

## 3. Review licenses and admit the uncommitted lock

Follow `docs/merlion/LOCK_ADMISSION.md`. Admission requires `BOOTSTRAP_PASS`, exact lock and
evidence hashes, a lock-only Git diff, expected HEAD, and approval for every registry package.

Only after `LOCK_ADMISSION_STATUS=ADMITTED` may the isolated lock be committed. The commit must
contain only `environments/merlion-core-py311/uv.lock`.

## 4. Certify the lock-only commit

Follow `docs/merlion/LOCK_COMMIT_CERTIFICATION.md`. Require:

```text
LOCK_COMMIT_STATUS=LOCK_COMMIT_CERTIFIED
```

This stage rechecks the commit parent, single-path diff, committed Git blob, workspace lock,
admission report, evidence ZIP, license review, clean worktree, and current HEAD.

## 5. Formal runtime certification

Pass the certified report explicitly so tmux does not depend on stale server environment values.

```bash
RUN_ID="<BOOTSTRAP_RUN_ID>"
REPORT="$PWD/artifacts/merlion-lock-admission/${RUN_ID}/LOCK_COMMIT_REPORT.json"
MERLION_LOCK_COMMIT_REPORT="$REPORT" \
SESSION=merlion-core-certification \
  bash scripts/start_merlion_core_certification_tmux.sh
```

The runtime script revalidates the report before `uv sync`. Isolated `uv sync` and provider
`uv run` use `--no-sources`.

Formal success requires `RUNTIME_CERTIFIED`, all three models `RUNTIME_VERIFIED`, distinct
train/load process IDs, prediction equality, package/version/revision agreement, and complete
SHA-256 verification.

## 6. Failure handling

Do not overwrite a failed Run, evidence ZIP, admission report, commit report, or decision. Fix only
the classified cause and use a new Run ID. Holdout and Prospective data remain closed here.
