[CmdletBinding()]
param(
    [string]$Repo = "arumajirou/loto_forecast_platform",
    [string]$OutputRoot,
    [switch]$Live,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot "artifacts\github-audit-verify"
}

$Uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $Uv) {
    throw "uv is required for the repository verification lane."
}

$ExitCode = 1
Push-Location $RepoRoot
try {
    Write-Host "=== GitHub audit focused verification ==="
    Write-Host "REPO_ROOT=$RepoRoot"
    Write-Host "TARGET_REPO=$Repo"
    Write-Host "RUN_LIVE=$Live"

    & $Uv.Source run python -m ruff format --check `
        src/loto/github_audit `
        tests/test_github_audit.py
    if ($LASTEXITCODE -ne 0) { throw "Ruff format check failed." }

    & $Uv.Source run python -m ruff check `
        src/loto/github_audit `
        tests/test_github_audit.py
    if ($LASTEXITCODE -ne 0) { throw "Ruff lint failed." }

    & $Uv.Source run python -m compileall -q `
        src/loto/github_audit `
        tests/test_github_audit.py
    if ($LASTEXITCODE -ne 0) { throw "compileall failed." }

    & $Uv.Source run python -m pytest -q tests/test_github_audit.py
    if ($LASTEXITCODE -ne 0) { throw "Focused pytest failed." }

    & $Uv.Source run loto-github-audit --self-test
    if ($LASTEXITCODE -ne 0) { throw "CLI self-test failed." }

    if ($Live) {
        gh auth status --hostname github.com
        if ($LASTEXITCODE -ne 0) { throw "GitHub CLI authentication failed." }
        New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
        & $Uv.Source run loto-github-audit `
            --repo $Repo `
            --output-root $OutputRoot `
            --max-items 100 `
            --max-action-runs 25 `
            --max-run-jobs 10 `
            --max-pr-details 10 `
            --max-issue-details 10
        if ($LASTEXITCODE -ne 0) { throw "Live GitHub audit smoke failed." }
    }

    Write-Host "VERIFICATION_STATUS=PASS"
    $ExitCode = 0
}
catch {
    Write-Error ($_ | Out-String)
    $ExitCode = 1
}
finally {
    Pop-Location
    Write-Host "EXIT_CODE=$ExitCode"
    if (-not $NoPause) {
        [void](Read-Host "Enterキーで終了します")
    }
}

exit $ExitCode
