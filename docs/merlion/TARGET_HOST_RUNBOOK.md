# Merlion core target-host runbook

## Status boundary

The preflight, bootstrap, evidence packaging, and certification stages are separate.

- Preflight checks uv, Python 3.11 availability, DNS, disk space, and writable paths.
- Bootstrap creates, audits, and syncs the isolated lock. It is not runtime certification.
- Evidence packaging preserves either `BOOTSTRAP_PASS` or `BOOTSTRAP_BLOCKED` without promotion.
- Formal certification requires the lock to be committed, the repository to be clean, and
  `uv sync --frozen` to pass.

## 1. Recommended one-command resume

The resume runner never uses sudo, never changes the system Python, and never updates shell
profiles. When Python 3.11 is absent and GitHub is reachable, uv installs a managed interpreter
under `artifacts/merlion-managed-python/` with `--no-bin`.

```bash
cd /mnt/e/env/ts/loto_forecast_platform
SESSION=merlion-core-bootstrap \
  bash scripts/start_merlion_core_bootstrap_tmux.sh
```

Monitor:

```bash
tmux attach -t merlion-core-bootstrap
```

The runner performs preflight, writes `BOOTSTRAP_PLAN.json`, provisions Python 3.11 only when
allowed, executes bootstrap with the exact interpreter path, and creates a verified evidence ZIP.

## 2. Evidence outputs

```text
artifacts/merlion-bootstrap/<RUN_ID>/PREFLIGHT.json
artifacts/merlion-bootstrap/<RUN_ID>/BOOTSTRAP_PLAN.json
artifacts/merlion-bootstrap/<RUN_ID>/PYTHON_PROVISION.log
artifacts/merlion-bootstrap/<RUN_ID>/PYTHON_PATH.txt
artifacts/merlion-bootstrap/<RUN_ID>/DEPENDENCY_AUDIT.json
artifacts/merlion-bootstrap/<RUN_ID>/DEPENDENCY_INVENTORY.csv
artifacts/merlion-bootstrap/<RUN_ID>/BOOTSTRAP_FAILURE.json
artifacts/merlion-bootstrap-packages/<RUN_ID>.zip
artifacts/merlion-bootstrap-packages/<RUN_ID>.zip.sha256
artifacts/merlion-bootstrap-packages/<RUN_ID>.verification.json
```

A blocked run still produces a ZIP. Verification confirms evidence integrity but does not change
`BOOTSTRAP_BLOCKED` into a success state.

## 3. Bootstrap safety

The bootstrap resolves one exact Python 3.11 executable and passes its path to every uv command.
It uses `--no-sources` for lock, sync, and run so workspace, Git, URL, and local source overrides
cannot silently enter the isolated environment.

Review `environments/merlion-core-py311/uv.lock`, package sources, versions, hashes, and licenses.
The lock contains no reliable license inventory; license review remains a separate required action.
Commit the isolated lock only after review. Do not modify the root lock.

## 4. Formal runtime certification

After the reviewed lock is committed, run from the exact clean commit:

```bash
cd /mnt/e/env/ts/loto_forecast_platform
SESSION=merlion-core-certification \
  bash scripts/start_merlion_core_certification_tmux.sh
```

Formal success requires `RUNTIME_CERTIFIED`, all three models `RUNTIME_VERIFIED`, distinct
train/load process IDs, prediction equality, package/version/revision agreement, and complete
SHA-256 verification.

## 5. Failure handling

Do not overwrite a failed Run. Preserve its Run ID and evidence ZIP. Fix only the classified
cause, run focused tests, and use a new Run ID. Do not open Holdout or Prospective data here.
