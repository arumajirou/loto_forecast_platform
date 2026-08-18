param(
    [string]$Phase7Root = "C:\Users\bp00425\Downloads\automlforecast-phase7-holdout-20260818-101611",
    [string]$Phase6CRoot = "C:\Users\bp00425\Downloads\automlforecast-phase6c-ensemble-freeze-20260818-101021",
    [string]$Phase6BRoot = "C:\Users\bp00425\Downloads\automlforecast-phase6b-multiseed-20260818-095723",
    [string]$Phase3Root = "C:\Users\bp00425\Downloads\automlforecast-phase3-input-size-20260817-173808",
    [string]$SmokeRoot = "C:\Users\bp00425\Downloads\automlforecast-api-smoke-20260817-163008",
    [switch]$PublishEvidence
)

$ErrorActionPreference = "Stop"
$FinalRC = 99
$RunId = Get-Date -Format "yyyyMMdd-HHmmss"
$EvidenceBranch = $null
$OriginalBranch = $null
$Log = $null
$Out = $null

try {
    $Repo = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
    if ([string]::IsNullOrWhiteSpace($Repo)) {
        throw "This tool must be run from a Git checkout."
    }

    $OriginalBranch = (& git -C $Repo branch --show-current).Trim()
    $RepoHead = (& git -C $Repo rev-parse HEAD).Trim()

    $Development = Join-Path $Phase3Root "artifacts\numbers3-development-only.csv"
    $Python = Join-Path $SmokeRoot "venv\Scripts\python.exe"
    $Script = Join-Path $PSScriptRoot "semantic_diagnosis.py"
    $Monitor = Join-Path $PSScriptRoot "monitor_semantic_diagnosis.ps1"

    if ($PublishEvidence) {
        $Dirty = @(& git -C $Repo status --porcelain=v1)
        if ($LASTEXITCODE -ne 0) {
            throw "git status failed."
        }
        if ($Dirty.Count -gt 0) {
            throw "PublishEvidence requires a clean working tree before diagnosis. Commit/stash unrelated changes first."
        }

        $EvidenceBranch = "evidence/phase7-semantic-diagnosis-$RunId"
        & git -C $Repo switch -c $EvidenceBranch
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create evidence branch: $EvidenceBranch"
        }
    }

    $Out = Join-Path $Repo "evidence\phase7_semantic_diagnosis\$RunId"
    $Log = Join-Path $Out "launcher.log"

    Write-Host "============================================================"
    Write-Host "PHASE 7 SEMANTIC DIAGNOSIS"
    Write-Host "============================================================"
    Write-Host "MODE=READ_ONLY_FORENSIC"
    Write-Host "REPO=$Repo"
    Write-Host "TOOL_REPO_HEAD=$RepoHead"
    Write-Host "FROZEN_EXPERIMENT_COMMIT=179bcbc9a51a60f0badfe7faa25f3818ab686229"
    Write-Host "HOLDOUT_EXPECTED=0/50"
    Write-Host "ACTUALS_EXPECTED=0"
    Write-Host "PUBLISH_EVIDENCE=$([bool]$PublishEvidence)"
    if ($EvidenceBranch) { Write-Host "EVIDENCE_BRANCH=$EvidenceBranch" }
    Write-Host "OUTPUT=$Out"
    Write-Host ""

    foreach ($Path in @($Python, $Script, $Monitor, $Repo, $Phase7Root, $Phase6CRoot, $Phase6BRoot, $Development)) {
        if (-not (Test-Path -LiteralPath $Path)) {
            throw "Required path missing: $Path"
        }
    }

    New-Item -ItemType Directory -Force -Path $Out | Out-Null

    $MonitorArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $Monitor + '" -Root "' + $Out + '"'
    Start-Process -FilePath "powershell.exe" -ArgumentList $MonitorArgs | Out-Null

    Write-Host "[1/5] Holdout integrity gate"
    Write-Host "[2/5] Development-only replay forensic comparison"

    $OldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Python $Script `
            --repo $Repo `
            --phase7-root $Phase7Root `
            --phase6c-root $Phase6CRoot `
            --phase6b-root $Phase6BRoot `
            --development $Development `
            --output $Out `
            2>&1 | Tee-Object -FilePath $Log
        $DiagnosisRC = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $OldPreference
    }

    if ($null -eq $DiagnosisRC) { $DiagnosisRC = 99 }
    Write-Host "[3/5] DIAGNOSIS_NATIVE_RC=$DiagnosisRC"

    Write-Host "[4/5] Verify SHA256SUMS"
    $Sums = Join-Path $Out "SHA256SUMS"
    if (-not (Test-Path -LiteralPath $Sums -PathType Leaf)) {
        throw "SHA256SUMS missing: $Sums"
    }

    $ChecksumFail = $false
    Get-Content -LiteralPath $Sums | ForEach-Object {
        if (-not [string]::IsNullOrWhiteSpace($_)) {
            $Parts = $_ -split '  ', 2
            if ($Parts.Count -ne 2) {
                $ChecksumFail = $true
            }
            else {
                $Expected = $Parts[0].Trim().ToLower()
                $Target = Join-Path $Out $Parts[1].Trim()
                if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
                    $ChecksumFail = $true
                }
                else {
                    $Actual = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLower()
                    if ($Actual -ne $Expected) { $ChecksumFail = $true }
                }
            }
        }
    }
    if ($ChecksumFail) {
        throw "SHA256SUMS verification failed"
    }
    Write-Host "SHA256SUMS=PASS" -ForegroundColor Green

    Write-Host "[5/5] Read final diagnosis"
    $DiagnosisPath = Join-Path $Out "DIAGNOSIS.json"
    if (-not (Test-Path -LiteralPath $DiagnosisPath -PathType Leaf)) {
        throw "DIAGNOSIS.json missing; inspect $Log"
    }

    $D = Get-Content -LiteralPath $DiagnosisPath -Raw | ConvertFrom-Json
    Write-Host "STATUS=$($D.status)"
    Write-Host "CLASSIFICATION=$($D.classification)"
    Write-Host "HOLDOUT_DRAWS_ACCESSED=$($D.holdout_draws_accessed)"
    Write-Host "ACTUALS_ACCESSED=$($D.actuals_accessed)"
    Write-Host "BEST_TRIAL_SAME=$($D.best_trial_same)"
    Write-Host "BEST_OBJECTIVE_SAME=$($D.best_objective_same)"
    Write-Host "TRIAL_PARAMS_SAME=$($D.trial_params_same)"
    Write-Host "SEMANTIC_VALUES_SAME=$($D.semantic_values_same)"
    Write-Host "VERSION_DRIFT=$($D.version_drift_detected)"
    Write-Host "TRUE_CONFIG_DRIFT=$($D.true_config_drift_detected)"
    Write-Host "SAFE_TO_CHANGE_VERIFIER=$($D.safe_to_change_verifier)"
    Write-Host "SAFE_TO_CONTINUE_HOLDOUT=$($D.safe_to_continue_holdout)"
    Write-Host "NEXT_ACTION=$($D.next_action)"

    if ([int]$D.holdout_draws_accessed -ne 0 -or [int]$D.actuals_accessed -ne 0) {
        throw "INTEGRITY FAILURE: Holdout/actual access is not zero."
    }
    Write-Host "HOLDOUT_INTEGRITY=PRESERVED" -ForegroundColor Green

    if ($PublishEvidence) {
        $RelativeOut = "evidence/phase7_semantic_diagnosis/$RunId"
        & git -C $Repo add -- $RelativeOut
        if ($LASTEXITCODE -ne 0) { throw "git add evidence failed" }

        & git -C $Repo diff --cached --quiet
        if ($LASTEXITCODE -eq 0) {
            throw "No evidence files were staged."
        }

        & git -C $Repo commit -m "evidence: phase7 semantic diagnosis $RunId"
        if ($LASTEXITCODE -ne 0) { throw "git commit evidence failed" }

        & git -C $Repo push -u origin $EvidenceBranch
        if ($LASTEXITCODE -ne 0) { throw "git push evidence branch failed" }

        $EvidenceCommit = (& git -C $Repo rev-parse HEAD).Trim()
        Write-Host "EVIDENCE_PUBLISHED=YES" -ForegroundColor Green
        Write-Host "EVIDENCE_BRANCH=$EvidenceBranch"
        Write-Host "EVIDENCE_COMMIT=$EvidenceCommit"
        Write-Host "EVIDENCE_PATH=$RelativeOut"
    }
    else {
        Write-Host "EVIDENCE_PUBLISHED=NO"
        Write-Host "To publish this evidence through GitHub, rerun from a clean checkout with -PublishEvidence."
    }

    # A non-serialization diagnosis is scientifically BLOCKED, but the launcher itself succeeded.
    $FinalRC = 0
}
catch {
    $FinalRC = 1
    Write-Host ""
    Write-Host "STATUS=BLOCKED" -ForegroundColor Red
    Write-Host "ERROR=$($_.Exception.Message)" -ForegroundColor Red
    if ($Out) { Write-Host "OUTPUT=$Out" }
    if ($EvidenceBranch) { Write-Host "EVIDENCE_BRANCH=$EvidenceBranch" }
}
finally {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "FINAL_LAUNCHER_RC=$FinalRC"
    if ($OriginalBranch) { Write-Host "ORIGINAL_BRANCH=$OriginalBranch" }
    if ($EvidenceBranch) { Write-Host "CURRENT_BRANCH=$EvidenceBranch" }
    if ($Log) { Write-Host "LOG=$Log" }
    Write-Host "============================================================"
    Write-Host ""
    Read-Host "Enterキーでターミナルに戻ります"
}
