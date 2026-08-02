[CmdletBinding(PositionalBinding=$false)]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$CommandArgs
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SharedRoot = Join-Path $Root 'shared-ai-memory'
$env:LOTO_OPS_PROJECT = $Root
if (-not $env:LOTO_OPS_CONFIG) { $env:LOTO_OPS_CONFIG = Join-Path $Root 'configs\loto_ops.yaml' }
if (-not $env:LOTO_OPS_RUNS_DIR) { $env:LOTO_OPS_RUNS_DIR = Join-Path $Root 'runs' }
if (-not $env:LOTO_HANDOVER_DIR) { $env:LOTO_HANDOVER_DIR = Join-Path $SharedRoot 'handovers' }
if (-not $env:LOTO_SKILLS_DIR) { $env:LOTO_SKILLS_DIR = Join-Path $SharedRoot 'skills' }
$env:PYTHONPATH = Join-Path $Root 'src'
if (-not $CommandArgs -or $CommandArgs.Count -eq 0) { $CommandArgs = @('--help') }
Push-Location $Root
try {
    & uv run --no-sync python -m loto_ops.cli --config $env:LOTO_OPS_CONFIG @CommandArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
