param(
    [string]$ProjectRoot = "C:\Users\bp00425\env\ts\loto_forecast_platform_v2",
    [ValidateSet("core","full","frameworks","tsfm","all")]
    [string]$Profile = "full",
    [string]$PythonVersion = "3.12"
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot\..
$Source = (Resolve-Path ".").Path
if ((Resolve-Path $ProjectRoot -ErrorAction SilentlyContinue) -and ((Resolve-Path $ProjectRoot).Path -ne $Source)) {
    $backup = "$ProjectRoot.bak.$(Get-Date -Format yyyyMMdd_HHmmss)"
    Move-Item -LiteralPath $ProjectRoot -Destination $backup
}
if ($Source -ne $ProjectRoot) { Copy-Item -LiteralPath $Source -Destination $ProjectRoot -Recurse }
Set-Location -LiteralPath $ProjectRoot
uv python find $PythonVersion *> $null
if ($LASTEXITCODE -ne 0) { uv python install $PythonVersion }
uv venv --python $PythonVersion --clear
$extras = switch ($Profile) {
  "core" { @("api","dev") }
  "full" { @("full","dev") }
  "frameworks" { @("full","frameworks","dev") }
  "tsfm" { @("full","tsfm","dev") }
  "all" { @("full","frameworks","tsfm","dev") }
}
$args = @("sync")
foreach ($extra in $extras) { $args += @("--extra", $extra) }
& uv @args
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
uv run pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
uv run loto config validate --file configs/research_smoke.yaml
Write-Host "Loto Forecast Platform v2 installed: $ProjectRoot" -ForegroundColor Green
