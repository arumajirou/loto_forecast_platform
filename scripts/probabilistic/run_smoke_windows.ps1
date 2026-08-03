param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [switch]$NoPause
)
$ErrorActionPreference = "Stop"
Set-Location $Root
uv run loto3 probabilistic smoke --config configs/probabilistic/smoke.yaml
if (-not $NoPause) { Read-Host "Press Enter to keep this window open and finish" }
