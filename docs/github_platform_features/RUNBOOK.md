# Runbook — GitHub Platform Features Foundation v1

## 1. Operating rules

- Use a fresh branch from current `main` for each feature.
- Keep PRs Draft until evidence is complete.
- Do not rerun zero-step Actions failures unless an external setting changed.
- Do not expose secret values, webhook URLs, private hostnames, local absolute paths, Holdout, or Prospective evidence.
- Do not enable auto-merge or alter production promotion from these workflows.

## 2. Pre-flight audit

### Linux/WSL

```bash
set -Eeuo pipefail
ROOT="/absolute/path/to/loto_forecast_platform"
LOG_DIR="$ROOT/artifacts/github-platform-preflight/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$LOG_DIR"
trap 'code=$?; printf "%s\n" "$code" > "$LOG_DIR/exit-code.txt"; echo "exit_code=$code"; read -r -p "Enterキーで終了します..." _; exit "$code"' EXIT
cd "$ROOT"
{
  git status --short --branch
  git branch --show-current
  git remote -v
  git rev-parse HEAD
  git fetch origin main
  git rev-parse origin/main
  gh auth status
  gh repo view arumajirou/loto_forecast_platform --json nameWithOwner,visibility,defaultBranchRef
} 2>&1 | tee "$LOG_DIR/preflight.log"
```

### Windows PowerShell

```powershell
$ErrorActionPreference = 'Stop'
$Root = 'E:\env\ts\loto_forecast_platform'
$RunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$LogDir = Join-Path $Root "artifacts\github-platform-preflight\$RunId"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $Root
try {
  & git status --short --branch *>&1 | Tee-Object "$LogDir\git-status.log"
  & git remote -v *>&1 | Tee-Object "$LogDir\git-remote.log"
  & git fetch origin main *>&1 | Tee-Object "$LogDir\git-fetch.log"
  & gh auth status *>&1 | Tee-Object "$LogDir\gh-auth.log"
  & gh repo view arumajirou/loto_forecast_platform --json nameWithOwner,visibility,defaultBranchRef *>&1 |
    Tee-Object "$LogDir\repo.json"
  '0' | Set-Content "$LogDir\exit-code.txt"
} catch {
  '1' | Set-Content "$LogDir\exit-code.txt"
  throw
} finally {
  Read-Host 'Enterキーで終了します...'
}
```

## 3. Issue #58 actions recovery

1. Open repository Settings → Actions → General.
2. Confirm Actions and GitHub-authored actions are allowed.
3. Confirm standard GitHub-hosted runners are permitted.
4. Inspect Settings → Actions → Runners and runner groups.
5. Inspect account billing, metered usage, budgets, storage, and payment restrictions.
6. Capture any UI banner without exposing payment details.
7. After a material setting change, run one workflow and verify jobs contain real steps.
8. Retain run ID, job IDs, step list, logs, conclusion, and screenshots.

Do not change feature code to fix a zero-step infrastructure failure without a concrete workflow error.

## 4. Dependabot operations

- Review each PR's manifest and lock diff.
- Verify compatibility-sensitive components separately.
- Run frozen sync and focused smoke before approval.
- Close superseded or duplicate PRs with a reason.
- Disable by reverting/removing `.github/dependabot.yml`; do not delete dependency evidence.

## 5. Projects operations

- Export field/view/workflow configuration after changes.
- Use Project only for governance status.
- Investigate cards stuck in Blocked or Verification.
- Never manually set Verified without linked evidence.
- Disable automation before bulk edits, archival, or deletion.

## 6. Pages operations

### Before deployment

- confirm visibility decision;
- run public-doc audit and strict build;
- inspect manifest and changed pages;
- verify no internal links or local paths;
- verify source commit.

### Incident response

If sensitive content is published:

1. Disable deployment workflow and Pages setting.
2. Preserve incident evidence.
3. Remove content through a normal revert/fix PR.
4. Revoke/rotate any exposed credential immediately.
5. Purge or invalidate caches where supported.
6. Document exposure window and affected URLs.
7. Re-enable only after security approval.

## 7. Webhook operations

### Health checks

- `/health` distinguishes receiver, store, queue, email, Project, and MLflow states.
- `/metrics` exposes bounded metrics.
- delivery backlog and dead letters are reviewed.

### Secret rotation

1. Generate a new high-entropy secret in approved secret storage.
2. Configure receiver with new active key and old previous key ID.
3. Update GitHub webhook secret.
4. Send test delivery and verify new key.
5. End bounded overlap and revoke old key.
6. Verify logs contain no secret or signature.

### Redelivery

- Confirm original delivery ID and failure reason.
- Fix receiver/dependency first.
- Use GitHub redelivery for failed deliveries.
- Deduplication must prevent repeated side effects.
- Record original and redelivery evidence.

### Dead letters

- Classify transient vs permanent.
- Never blindly replay invalid signatures or malformed payloads.
- Replay valid events under a new processing Run ID while retaining original delivery identity.

## 8. Security scanning operations

- Scanner exit nonzero due to findings is distinct from scanner crash.
- Empty or missing report is not clean.
- Suppressions require reason, owner, scope, and review date.
- Required checks are enabled only after stable successful runs.
- CodeQL remains disabled while eligibility is unverified.

## 9. Rollback verification

After rollback:

- compare repository settings/files to pre-change export;
- verify endpoint or workflow is disabled;
- verify queued work is drained/preserved;
- verify public content is unavailable when Pages is disabled;
- verify secrets are rotated when necessary;
- retain logs, manifests, hashes, and operator identity.

## 10. Escalation

Escalate to repository administrator for Actions/Pages/Code Security settings, security lead for exposure or signature incidents, MLOps lead for MLflow linkage, and promotion owner for any suspected registry or production side effect.