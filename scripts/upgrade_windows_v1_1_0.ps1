param(
  [string]$ZipRoot = "C:\Users\bp00425\env\ts\zip",
  [string]$TsRoot = "C:\Users\bp00425\env\ts"
)
$ErrorActionPreference = "Stop"
$zip = Join-Path $ZipRoot "loto_forecast_platform_integrated_v1.1.0.zip"
$hashFile = Join-Path $ZipRoot "loto_forecast_platform_integrated_v1.1.0.sha256"
$project = Join-Path $TsRoot "loto_forecast_platform"
$stage = Join-Path $TsRoot "_extract_loto_forecast_platform_v1_1_0"
$expected = ((Get-Content -LiteralPath $hashFile -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($expected -ne $actual) { throw "SHA-256 mismatch" }
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
$root = Join-Path $stage "loto_forecast_platform_integrated"
if (-not (Test-Path $root)) { throw "Archive root not found: $root" }
if (Test-Path $project) {
  $backup = "${project}.bak.$(Get-Date -Format yyyyMMdd_HHmmss)"
  Move-Item -LiteralPath $project -Destination $backup
  Write-Host "Previous version: $backup"
}
Move-Item -LiteralPath $root -Destination $project
Remove-Item $stage -Recurse -Force
Set-Location $project
uv python install 3.12
uv venv --python 3.12 --clear
uv sync --extra full --extra dev
& .\scripts\set_windows_secrets.ps1
uv run pytest -q
Write-Host "Installed: $project" -ForegroundColor Green
