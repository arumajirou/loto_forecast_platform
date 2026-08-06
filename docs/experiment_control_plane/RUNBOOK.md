# Runbook

## Before enqueue

```text
[ ] latest main and Plan commit recorded
[ ] plan hash recomputed
[ ] approval exact-subject/scope/expiry verified
[ ] lane capacity and budget available
[ ] data/protocol/model revisions pinned
[ ] Holdout/Prospective flags closed unless separately approved
[ ] object store, MLflow and DB health checked
[ ] no credentials in plan/evidence URIs
```

## Linux durable execution template

```bash
set -Eeuo pipefail
ROOT="/absolute/path/to/loto_forecast_platform"
RUN_ID="<run-id>"
LOG_ROOT="/absolute/path/to/logs/${RUN_ID}"
mkdir -p "$LOG_ROOT"
cd "$ROOT"

trap 'rc=$?; printf "%s\n" "$rc" >"$LOG_ROOT/exit_code"; echo "exit_code=$rc" | tee -a "$LOG_ROOT/launcher.log"; read -r -p "Enterキーで終了します..." _ || true' EXIT

systemd-run --user \
  --unit="loto-experiment-${RUN_ID}" \
  --property=Restart=no \
  --collect \
  /usr/bin/bash -lc \
  "cd '$ROOT' && uv run loto3 experiment-agent execute --run-id '$RUN_ID' 2>&1 | tee '$LOG_ROOT/run.log'"
```

Use the implemented agent command, exact absolute paths and its own secret injection mechanism. Do not paste tokens into shell history.

## Windows PowerShell durable launcher pattern

```powershell
$ErrorActionPreference = 'Stop'
$Root = 'E:\env\ts\loto_forecast_platform'
$RunId = '<run-id>'
$LogRoot = "E:\env\logs\$RunId"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
Set-Location $Root

try {
  & uv run loto3 experiment-agent execute --run-id $RunId *>&1 |
    Tee-Object -FilePath (Join-Path $LogRoot 'run.log')
  $rc = $LASTEXITCODE
} catch {
  $_ | Out-File (Join-Path $LogRoot 'launcher-error.log')
  $rc = 1
} finally {
  $rc | Out-File (Join-Path $LogRoot 'exit_code')
  Read-Host 'Enterキーで終了します...'
}
exit $rc
```

For terminal-independent execution, install the final agent as a Windows service or Scheduled Task under a restricted account.

## Failure triage

1. Record symptom, Run ID, event revision, lease/fence and last known good state.
2. Preserve logs, process/GPU state and evidence hashes before remediation.
3. Classify control, execution, evidence, projection, infrastructure or policy failure.
4. Reproduce with the smallest synthetic case.
5. Form hypotheses ordered by risk and verification cost.
6. Test without overwriting the failed Run ID.
7. Repair via a new event/attempt and retain the original failure.

## Common classifications

- `CI_BLOCKED_PRE_RUN`: no workflow steps; inspect Issue #58/settings, do not edit feature code blindly.
- `LEASE_LOST`: stop publishing, seal local logs and wait for controller decision.
- `EVIDENCE_HASH_MISMATCH`: quarantine bytes and result; never re-label as verified.
- `PROJECTION_FAILED`: canonical state remains valid; retry/reconcile GitHub projection.
- `BUDGET_EXCEEDED`: stop new paid requests, seal cost evidence, require new plan/approval.
- `CPU_FALLBACK`: fail runtime certification for a GPU-required lane.

## Recovery

- Controller restart: replay event/outbox logs, verify revisions and resume projection.
- Agent restart: re-authenticate, reacquire only if allowed, compare fence and sealed workspace.
- Storage recovery: verify object digest before linking or completing.
- GitHub recovery: replay outbox idempotently and compare displayed source revision.

## Shutdown and VRAM release

Verify process exit, child-process cleanup, model unload, CUDA context/PID disappearance, VRAM return within tolerance and final heartbeat/receipt. A successful prediction without unload/VRAM evidence is only partially verified for a formal GPU run.
