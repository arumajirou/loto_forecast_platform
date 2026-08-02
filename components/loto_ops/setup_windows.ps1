[CmdletBinding()]
param(
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SharedRoot = Join-Path $Root 'shared-ai-memory'
$env:LOTO_OPS_PROJECT = $Root
$env:LOTO_OPS_CONFIG = Join-Path $Root 'configs\loto_ops.yaml'
$env:LOTO_OPS_RUNS_DIR = Join-Path $Root 'runs'
$env:LOTO_HANDOVER_DIR = Join-Path $SharedRoot 'handovers'
$env:LOTO_SKILLS_DIR = Join-Path $SharedRoot 'skills'
$env:PYTHONPATH = (Join-Path $Root 'src')
New-Item -ItemType Directory -Force -Path $env:LOTO_OPS_RUNS_DIR, $env:LOTO_HANDOVER_DIR, $env:LOTO_SKILLS_DIR | Out-Null
Copy-Item -Recurse -Force (Join-Path $Root 'skills\*') $env:LOTO_SKILLS_DIR

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required. Install uv and rerun setup_windows.ps1.'
}
Push-Location $Root
try {
    uv sync --frozen --all-groups --extra web
    if ($LASTEXITCODE -ne 0) { throw 'uv sync failed.' }
    uv run --no-sync python -m compileall -q src tests
    if ($LASTEXITCODE -ne 0) { throw 'compileall failed.' }
    uv run --no-sync python -m loto_ops.cli --help | Out-Null
    uv run --no-sync python -m loto_ops.cli --config $env:LOTO_OPS_CONFIG run --dry-run
    if (-not $SkipTests) {
        uv run --no-sync pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }
    }
    Write-Host 'SETUP PASS'
    Write-Host "Run: .\run_loto_ops.ps1 --help"
} finally {
    Pop-Location
}
