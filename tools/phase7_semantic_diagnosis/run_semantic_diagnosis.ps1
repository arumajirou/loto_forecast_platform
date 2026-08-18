param(
    [string]$Phase7Root = "C:\Users\bp00425\Downloads\automlforecast-phase7-holdout-20260818-101611",
    [string]$Phase6CRoot = "C:\Users\bp00425\Downloads\automlforecast-phase6c-ensemble-freeze-20260818-101021",
    [string]$Phase6BRoot = "C:\Users\bp00425\Downloads\automlforecast-phase6b-multiseed-20260818-095723",
    [string]$Phase3Root = "C:\Users\bp00425\Downloads\automlforecast-phase3-input-size-20260817-173808",
    [string]$SmokeRoot = "C:\Users\bp00425\Downloads\automlforecast-api-smoke-20260817-163008",
    [string]$Repository = "arumajirou/loto_forecast_platform",
    [string]$OutputRoot = "",
    [switch]$PublishEvidence
)

$ErrorActionPreference = "Stop"
$Implementation = Join-Path $PSScriptRoot "run_semantic_diagnosis_impl.ps1"
$TempLauncher = Join-Path $PSScriptRoot (".phase7-semantic-diagnosis-ps51-" + [Guid]::NewGuid().ToString("N") + ".ps1")

try {
    if (-not (Test-Path -LiteralPath $Implementation -PathType Leaf)) {
        throw "Phase 7 implementation launcher missing: $Implementation"
    }

    $Utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false, $true
    $Utf8Bom = New-Object System.Text.UTF8Encoding -ArgumentList $true
    $Text = [System.IO.File]::ReadAllText($Implementation, $Utf8)
    [System.IO.File]::WriteAllText($TempLauncher, $Text, $Utf8Bom)

    $InvokeArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $TempLauncher,
        "-Phase7Root", $Phase7Root,
        "-Phase6CRoot", $Phase6CRoot,
        "-Phase6BRoot", $Phase6BRoot,
        "-Phase3Root", $Phase3Root,
        "-SmokeRoot", $SmokeRoot,
        "-Repository", $Repository
    )
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
        $InvokeArgs += @("-OutputRoot", $OutputRoot)
    }
    if ($PublishEvidence) {
        $InvokeArgs += "-PublishEvidence"
    }

    & powershell.exe @InvokeArgs
    $NativeRC = $LASTEXITCODE
    if ($NativeRC -ne 0) {
        throw "Phase 7 semantic diagnosis implementation failed with rc=$NativeRC"
    }
}
finally {
    if (Test-Path -LiteralPath $TempLauncher) {
        Remove-Item -LiteralPath $TempLauncher -Force -ErrorAction SilentlyContinue
    }
}
