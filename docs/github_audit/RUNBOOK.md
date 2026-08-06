# GitHub Repository Audit Runbook

## 1. Purpose

Operate the repository audit exporter on Linux, WSL, or Windows without changing
the audited GitHub repository.

## 2. Preconditions

- checkout contains `loto-github-audit`
- Python 3.11+
- `uv`
- GitHub CLI `gh`
- authenticated access to the target repository

Verify authentication:

```bash
gh auth status --hostname github.com
```

The token may need repository, organization-read, workflow, and security-event
permissions for complete coverage. Missing optional permissions are recorded as
endpoint gaps rather than silently converted to zero alerts.

## 3. Focused local verification

Linux / WSL:

```bash
bash scripts/verify_github_audit.sh
```

Windows:

```powershell
.\scripts\verify_github_audit.ps1
```

Do not start a live audit if focused verification fails.

## 4. Lightweight audit

Linux / WSL:

```bash
uv run loto-github-audit \
  --repo arumajirou/loto_forecast_platform \
  --output-root artifacts/github-audit
```

Windows:

```powershell
uv run loto-github-audit `
  --repo arumajirou/loto_forecast_platform `
  --output-root artifacts\github-audit
```

Use this lane for routine repository, Actions, security, dependency, and settings
snapshots without per-PR and per-Issue expansion.

## 5. Deep audit

Linux / WSL:

```bash
bash scripts/run_github_audit.sh
```

Windows:

```powershell
.\scripts\run_github_audit.ps1 -Deep
```

Deep mode expands open Issues, open PR reviews and review threads, changed files,
checks, workflow runs, and selected Actions jobs. It can consume many API calls.
Reduce `--max-*` limits when approaching the API rate limit.

## 6. Live verification smoke

Linux / WSL:

```bash
GITHUB_AUDIT_LIVE=1 bash scripts/verify_github_audit.sh
```

Windows:

```powershell
.\scripts\verify_github_audit.ps1 -Live
```

The smoke is intentionally bounded and does not enable `--deep`.

## 7. Result interpretation

- `VERIFIED`: all requested endpoints were captured
- `VERIFIED_WITH_GAPS`: optional endpoints were unavailable
- `PARTIALLY_VERIFIED`: at least one core endpoint was unavailable
- `BLOCKED`: authentication or permission prevented access
- `NOT_APPLICABLE`: current repository configuration does not use the endpoint
- `NOT_AVAILABLE`: feature disabled, absent, unsupported, or returned 404
- `RATE_LIMITED`: GitHub API rate limit prevented collection
- `FAILED`: unclassified acquisition or artifact failure

Exit codes:

- `0`: artifacts generated and core endpoints available
- `1`: execution, authentication, or artifact-generation failure
- `2`: core endpoint gap
- `130`: user interruption

## 8. Required artifacts

Confirm each run contains:

```text
REPORT.md
REPORT.html
SUMMARY.json
MANUAL_CHECKS.md
ARTIFACT_MANIFEST.json
SHA256SUMS
status.txt
exit_code.txt
tables/endpoint_status.csv
```

Confirm the sibling ZIP and `.zip.sha256` files exist.

## 9. Integrity verification

Linux:

```bash
cd <audit-run-directory>
sha256sum -c SHA256SUMS
cd ..
sha256sum -c <audit-run>.zip.sha256
unzip -t <audit-run>.zip
```

Windows PowerShell:

```powershell
Get-FileHash <audit-run>.zip -Algorithm SHA256
Expand-Archive <audit-run>.zip -DestinationPath .\zip-check -Force
```

Compare the calculated ZIP hash with the sibling `.zip.sha256` file.

## 10. Incident handling

### Authentication failure

Run `gh auth status`. Reauthenticate with `gh auth login` or refresh the required
scopes. Do not place tokens in command-line arguments or report files.

### Optional endpoint blocked

Use `tables/endpoint_status.csv` to identify the permission or unavailable feature.
The run may remain operationally useful as `VERIFIED_WITH_GAPS`.

### Core endpoint blocked

Treat exit code `2` as incomplete evidence. Do not use the report as a complete
repository state snapshot.

### Actions run has zero steps

Classify it as a GitHub Actions pre-run/control-plane blocker. It is not evidence
that repository tests executed or failed.

### Rate limited

Preserve the partial run, reduce deep limits, wait for reset, and create a new run.
Do not overwrite the prior raw evidence.
