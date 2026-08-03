param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [string]$Config = "",
    [switch]$NoPause
)
$ErrorActionPreference = "Stop"
$TimeStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogDir = Join-Path $Root "artifacts\probabilistic-native-smoke-$TimeStamp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not $Config) { $Config = Join-Path $Root "configs\probabilistic\native_smoke.yaml" }

try {
    Set-Location $Root
    uv run python tools\verify_native_ppl_implementation.py `
        --root $Root `
        --require-runtime `
        --output (Join-Path $LogDir "native-verification.json")
    if ($LASTEXITCODE -ne 0) { throw "native runtime verification failed" }

    uv run loto3 probabilistic native-coverage |
        Out-File -Encoding utf8 (Join-Path $LogDir "native-coverage.json")
    uv run loto3 probabilistic plan --config $Config |
        Out-File -Encoding utf8 (Join-Path $LogDir "plan.json")

    $Plan = Get-Content -Raw (Join-Path $LogDir "plan.json") | ConvertFrom-Json
    if ($Plan.models_requested -ne 72 -or
        $Plan.trials_total -ne 72 -or
        $Plan.trials_allowed -ne 72 -or
        $Plan.trials_blocked -ne 0) {
        throw "native plan is not 72 allowed / 0 blocked"
    }
    Write-Host "PPL01_NATIVE_PLAN=PASS"

    uv run loto3 probabilistic smoke --config $Config |
        Tee-Object -FilePath (Join-Path $LogDir "run.json")
    if ($LASTEXITCODE -ne 0) { throw "native smoke returned exit code $LASTEXITCODE" }

    $Run = Get-Content -Raw (Join-Path $LogDir "run.json") | ConvertFrom-Json
    if ($Run.status -ne "PASS" -or
        $Run.models_planned -ne 72 -or
        $Run.trials_total -ne 72 -or
        $Run.status_counts.PASS -ne 72) {
        throw "native smoke did not return PASS 72/72"
    }
    Write-Host "PPL01_NATIVE_SMOKE=PASS"
    Write-Host "LOG_DIR=$LogDir"
}
finally {
    if (-not $NoPause) { Read-Host "Press Enter to keep this window open and finish" }
}
