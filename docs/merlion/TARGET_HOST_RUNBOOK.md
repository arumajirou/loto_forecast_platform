# Merlion core target-host runbook

## Status boundary

Preflight, bootstrap, evidence packaging, lock admission, and runtime certification are separate.

- Preflight checks uv, Python 3.11 availability, DNS, disk space, and writable paths.
- Bootstrap creates, audits, and syncs the isolated lock. It is not runtime certification.
- Evidence packaging preserves either `BOOTSTRAP_PASS` or `BOOTSTRAP_BLOCKED` without promotion.
- Lock admission binds the successful evidence, workspace lock, Git scope, and license review.
- Formal certification requires an admitted lock committed from an exact clean repository state.

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

## 3. Review licenses and admit the lock

Follow `docs/merlion/LOCK_ADMISSION.md`. Admission requires `BOOTSTRAP_PASS`, exact lock and
evidence hashes, a lock-only Git diff, expected HEAD, and approval for every registry package.

The license finalizer preserves human package decisions, rejects unresolved entries, and adds the
review self-hash. The admission command does not commit.


Only after `LOCK_ADMISSION_STATUS=ADMITTED` may the reviewed isolated lock be
committed in a separate intentional lock-only commit.

## 4. Formal runtime certification

After the admitted lock is committed, run from the exact clean commit:

```bash
SESSION=merlion-core-certification \
  bash scripts/start_merlion_core_certification_tmux.sh
```

Formal success requires `RUNTIME_CERTIFIED`, all three models `RUNTIME_VERIFIED`, distinct
train/load process IDs, prediction equality, package/version/revision agreement, and complete
SHA-256 verification.

## 5. Failure handling

Do not overwrite a failed Run, evidence ZIP, admission report, or decision. Fix only the classified
cause and use a new Run ID. Holdout and Prospective data remain closed in this phase.
