param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [ValidateSet("reference", "native", "all", "pymc", "jax", "pyro", "stan", "tfp")]
    [string]$Mode = "reference",
    [switch]$NoPause
)
$ErrorActionPreference = "Stop"
$TimeStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogDir = Join-Path $Root "artifacts\install\probabilistic-$TimeStamp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Transcript = Join-Path $LogDir "install.log"
Start-Transcript -Path $Transcript -Force
try {
    Set-Location $Root
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv is required. Install it before continuing."
    }
    uv sync --frozen --extra dev
    switch ($Mode) {
        "native" { uv pip install -r requirements-probabilistic-native.txt }
        "all" {
            uv pip install -r requirements-probabilistic-native.txt
            uv pip install -r requirements-probabilistic-stan.txt
            try { uv pip install -r requirements-probabilistic-tfp.txt } catch { Write-Warning $_ }
        }
        "pymc" { uv pip install -r requirements-probabilistic-pymc.txt }
        "jax"  { uv pip install -r requirements-probabilistic-jax.txt }
        "pyro" { uv pip install -r requirements-probabilistic-pyro.txt }
        "stan" { uv pip install -r requirements-probabilistic-stan.txt }
        "tfp"  { uv pip install -r requirements-probabilistic-tfp.txt }
    }

    uv run loto3 probabilistic catalog-list |
        Out-File -Encoding utf8 (Join-Path $LogDir "catalog.json")
    uv run loto3 probabilistic native-coverage |
        Out-File -Encoding utf8 (Join-Path $LogDir "native-coverage.json")
    uv run loto3 probabilistic backends |
        Out-File -Encoding utf8 (Join-Path $LogDir "backends.json")

    if ($Mode -in @("native", "all")) {
        uv run loto3 probabilistic validate-config --config configs/probabilistic/native_smoke.yaml |
            Out-File -Encoding utf8 (Join-Path $LogDir "config-validation.json")
        uv run python tools\verify_native_ppl_implementation.py `
            --root $Root `
            --require-runtime `
            --output (Join-Path $LogDir "native-verification.json")
    }
    else {
        uv run loto3 probabilistic validate-config --config configs/probabilistic/smoke.yaml |
            Out-File -Encoding utf8 (Join-Path $LogDir "config-validation.json")
        uv run python tools\verify_native_ppl_implementation.py `
            --root $Root `
            --output (Join-Path $LogDir "native-static-verification.json")
    }
    Write-Host "INSTALL_STATUS=PASS"
    Write-Host "LOG_DIR=$LogDir"
}
finally {
    Stop-Transcript
    if (-not $NoPause) { Read-Host "Press Enter to keep this window open and finish" }
}
