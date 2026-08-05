# Merlion core target-host runbook

## Status boundary

The bootstrap and certification stages are deliberately separate.

- Bootstrap creates and syncs the isolated lock. It is not runtime certification.
- Formal certification requires the lock to be committed, the repository to be clean, and
  `uv sync --frozen` to pass.
- A valid `BLOCKED` evidence bundle proves only that the failed attempt was recorded correctly.

## 1. Bootstrap and review the lock

```bash
cd /mnt/e/env/ts/loto_forecast_platform
RUN_ID="merlion-bootstrap-$(date -u +%Y%m%dT%H%M%SZ)" \
  bash scripts/bootstrap_merlion_core_env.sh
```

Review `environments/merlion-core-py311/uv.lock`, its package sources, versions, hashes, and
licenses. Commit it only after review. Do not modify the root lock.

## 2. Formal certification

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

## 3. Failure handling

Do not overwrite a failed Run. Preserve its Run ID and evidence. Fix only the classified cause,
run focused tests, and use a new Run ID. Do not open Holdout or Prospective data in this phase.
