[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\Users\bp00425\env\forecast\v3.2.0\loto_forecast_platform_v3.0.1",
    [string]$Config = "configs\auto_coverage_all_loto.yaml",
    [switch]$AcquireData,
    [switch]$NoLLM
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $ProjectRoot
$ConfigPath = Join-Path $ProjectRoot $Config
if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Config not found: $ConfigPath" }
if ($AcquireData) {
  foreach ($Game in @("mini", "loto6", "loto7")) {
    uv run loto data acquire --game $Game --output "runs\data-acquisition-$Game" --force
    if ($LASTEXITCODE -ne 0) { throw "Data acquisition failed: $Game" }
  }
}
if ($NoLLM) {
  $Text = Get-Content -LiteralPath $ConfigPath -Raw
  $Temp = Join-Path $env:TEMP "auto-coverage-no-llm.yaml"
  $Text = $Text -replace '(?ms)(local_llm:\s*\r?\n\s*enabled:)\s*true', '$1 false'
  [IO.File]::WriteAllText($Temp, $Text, [Text.UTF8Encoding]::new($false))
  $ConfigPath = $Temp
}
$env:OMP_NUM_THREADS = "6"
$env:MKL_NUM_THREADS = "6"
$env:OPENBLAS_NUM_THREADS = "6"
$env:NUMEXPR_NUM_THREADS = "6"
uv run loto experiment auto-coverage --config $ConfigPath
if ($LASTEXITCODE -ne 0) { throw "Auto coverage loop failed with exit code $LASTEXITCODE" }
