# Merlion core target-host runbook

## Status boundary

The preflight, bootstrap, and certification stages are deliberately separate.

- Preflight checks uv, Python 3.11 availability, DNS, disk space, and writable paths.
- Bootstrap creates, audits, and syncs the isolated lock. It is not runtime certification.
- Formal certification requires the lock to be committed, the repository to be clean, and
  `uv sync --frozen` to pass.
- A valid `BLOCKED` evidence bundle proves only that the failed attempt was recorded correctly.

## 1. Preflight

```bash
cd /mnt/e/env/ts/loto_forecast_platform
PYTHONPATH="$PWD/src" python3 scripts/run_merlion_core_preflight.py \
  --root "$PWD" \
  --output artifacts/merlion-preflight/manual/PREFLIGHT.json
```

`BLOCKED` must be resolved before dependency work. `DEGRADED` means bootstrap may use a local
cache but network-backed resolution is not currently available.

## 2. Bootstrap and review the lock

```bash
cd /mnt/e/env/ts/loto_forecast_platform
RUN_ID="merlion-bootstrap-$(date -u +%Y%m%dT%H%M%SZ)" \
  bash scripts/bootstrap_merlion_core_env.sh
```

Inspect:

```text
PREFLIGHT.json
DEPENDENCY_AUDIT.json
DEPENDENCY_INVENTORY.csv
dependency-sha256.txt
bootstrap.log
exit_code
BOOTSTRAP_FAILURE.json  # only when blocked
```

Review `environments/merlion-core-py311/uv.lock`, package sources, versions, and hashes. The lock
contains no reliable license inventory; license review remains a separate required action. Commit
the isolated lock only after review. Do not modify the root lock.

## 3. Formal certification

Run in tmux so terminal closure does not lose execution or logs.

```bash
cd /mnt/e/env/ts/loto_forecast_platform
SESSION=merlion-core-certification \
  bash scripts/start_merlion_core_certification_tmux.sh
```

Inspect:

```text
IDENTITY.json
DISCOVERY.json
MODEL_RUNTIME_MATRIX.json
VERIFICATION_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
provider-work/models/**
```

Formal success requires `RUNTIME_CERTIFIED`, all three models `RUNTIME_VERIFIED`, distinct
train/load process IDs, prediction equality, package/version/revision agreement, and complete
SHA-256 verification.

## 4. Failure handling

Do not overwrite a failed Run. Preserve its Run ID and evidence. Fix only the classified cause,
run focused tests, and use a new Run ID. Do not open Holdout or Prospective data in this phase.
