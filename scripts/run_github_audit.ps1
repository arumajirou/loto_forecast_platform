[CmdletBinding()]
param(
    [string]$Repo = "arumajirou/loto_forecast_platform",
    [string]$OutputRoot,
    [switch]$Deep,
    [switch]$NoPause,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AdditionalArguments
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot "artifacts\github-audit"
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

$Arguments = @(
    "--repo", $Repo,
    "--output-root", $OutputRoot
)
if ($Deep) {
    $Arguments += "--deep"
}
if ($AdditionalArguments) {
    $Arguments += $AdditionalArguments
}

$ExitCode = 1
try {
    Write-Host "REPO=$Repo"
    Write-Host "OUTPUT_ROOT=$OutputRoot"
    Write-Host "DEEP=$Deep"

    $Uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($Uv) {
        Push-Location $RepoRoot
        try {
            & $Uv.Source run loto-github-audit @Arguments
            $ExitCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }
    else {
        $Python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Python) {
            $Python = Get-Command py -ErrorAction SilentlyContinue
        }
        if (-not $Python) {
            throw "uv or Python 3 is required."
        }

        $OldPythonPath = $env:PYTHONPATH
        $env:PYTHONPATH = Join-Path $RepoRoot "src"
        if ($OldPythonPath) {
            $env:PYTHONPATH = "$($env:PYTHONPATH);$OldPythonPath"
        }
        Push-Location $RepoRoot
        try {
            if ($Python.Name -eq "py.exe" -or $Python.Name -eq "py") {
                & $Python.Source -3 -m loto.github_audit.cli @Arguments
            }
            else {
                & $Python.Source -m loto.github_audit.cli @Arguments
            }
            $ExitCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
            $env:PYTHONPATH = $OldPythonPath
        }
    }
}
catch {
    Write-Error ($_ | Out-String)
    $ExitCode = 1
}
finally {
    Write-Host "EXIT_CODE=$ExitCode"
    if (-not $NoPause) {
        [void](Read-Host "Enterキーで終了します")
    }
}

exit $ExitCode
