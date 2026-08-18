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
$FinalRC = 99
$RunId = Get-Date -Format "yyyyMMdd-HHmmss"
$EvidenceBranch = "evidence/phase7-semantic-diagnosis-$RunId"
$EvidenceCommit = $null
$Log = $null
$Out = $null

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )
    $Encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($Path, $Text, $Encoding)
}

function Invoke-GhJson {
    param(
        [Parameter(Mandatory = $true)][string]$Endpoint,
        [ValidateSet("GET", "POST")][string]$Method = "GET",
        [object]$Body = $null
    )

    $TempJson = $null
    try {
        $GhArgs = @("api")
        if ($Method -ne "GET") {
            $GhArgs += @("--method", $Method)
        }
        $GhArgs += $Endpoint

        if ($null -ne $Body) {
            $TempJson = Join-Path ([System.IO.Path]::GetTempPath()) ("phase7-gh-" + [Guid]::NewGuid().ToString("N") + ".json")
            Write-Utf8NoBom -Path $TempJson -Text ($Body | ConvertTo-Json -Depth 32)
            $GhArgs += @("--input", $TempJson)
        }

        $Raw = & gh @GhArgs 2>&1
        $Rc = $LASTEXITCODE
        $Text = ($Raw | Out-String).Trim()

        if ($Rc -ne 0) {
            throw "gh api failed (rc=$Rc): $Endpoint`n$Text"
        }
        if ([string]::IsNullOrWhiteSpace($Text)) {
            return $null
        }
        return ($Text | ConvertFrom-Json)
    }
    finally {
        if ($TempJson -and (Test-Path -LiteralPath $TempJson)) {
            Remove-Item -LiteralPath $TempJson -Force -ErrorAction SilentlyContinue
        }
    }
}

function Publish-EvidenceServerSide {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryName,
        [Parameter(Mandatory = $true)][string]$LocalOutput,
        [Parameter(Mandatory = $true)][string]$RunIdentifier,
        [Parameter(Mandatory = $true)][string]$BranchName
    )

    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "PublishEvidence requires GitHub CLI (gh), but gh was not found."
    }

    & gh auth status 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "PublishEvidence requires an authenticated gh session. Run: gh auth login"
    }

    $RemoteRepo = (& gh repo view $RepositoryName --json nameWithOwner --jq ".nameWithOwner" 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $RemoteRepo -ne $RepositoryName) {
        throw "Unable to verify GitHub repository identity: expected $RepositoryName, got '$RemoteRepo'."
    }

    $Main = Invoke-GhJson -Endpoint "repos/$RepositoryName/branches/main"
    $BaseCommit = [string]$Main.commit.sha
    if ([string]::IsNullOrWhiteSpace($BaseCommit)) {
        throw "Unable to resolve remote main commit."
    }

    $BaseCommitDoc = Invoke-GhJson -Endpoint "repos/$RepositoryName/git/commits/$BaseCommit"
    $BaseTree = [string]$BaseCommitDoc.tree.sha
    if ([string]::IsNullOrWhiteSpace($BaseTree)) {
        throw "Unable to resolve remote main tree."
    }

    $Files = @(Get-ChildItem -LiteralPath $LocalOutput -File -Recurse | Sort-Object FullName)
    if ($Files.Count -eq 0) {
        throw "No diagnosis evidence files found under $LocalOutput"
    }

    $TreeEntries = @()
    foreach ($File in $Files) {
        $Relative = $File.FullName.Substring($LocalOutput.Length).TrimStart([char[]]@('\', '/')) -replace "\\", "/"
        $RemotePath = "evidence/phase7_semantic_diagnosis/$RunIdentifier/$Relative"
        $Base64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($File.FullName))
        $Blob = Invoke-GhJson -Endpoint "repos/$RepositoryName/git/blobs" -Method "POST" -Body @{
            content = $Base64
            encoding = "base64"
        }
        if ([string]::IsNullOrWhiteSpace([string]$Blob.sha)) {
            throw "GitHub blob creation returned no SHA for $Relative"
        }
        $TreeEntries += @{
            path = $RemotePath
            mode = "100644"
            type = "blob"
            sha = [string]$Blob.sha
        }
    }

    $Tree = Invoke-GhJson -Endpoint "repos/$RepositoryName/git/trees" -Method "POST" -Body @{
        base_tree = $BaseTree
        tree = $TreeEntries
    }
    if ([string]::IsNullOrWhiteSpace([string]$Tree.sha)) {
        throw "GitHub tree creation returned no SHA."
    }

    $Commit = Invoke-GhJson -Endpoint "repos/$RepositoryName/git/commits" -Method "POST" -Body @{
        message = "evidence: phase7 semantic diagnosis $RunIdentifier"
        tree = [string]$Tree.sha
        parents = @($BaseCommit)
    }
    if ([string]::IsNullOrWhiteSpace([string]$Commit.sha)) {
        throw "GitHub commit creation returned no SHA."
    }

    $CreatedRef = Invoke-GhJson -Endpoint "repos/$RepositoryName/git/refs" -Method "POST" -Body @{
        ref = "refs/heads/$BranchName"
        sha = [string]$Commit.sha
    }
    if ([string]::IsNullOrWhiteSpace([string]$CreatedRef.object.sha)) {
        throw "GitHub branch creation returned no commit SHA."
    }

    $VerifyRef = Invoke-GhJson -Endpoint "repos/$RepositoryName/git/ref/heads/$BranchName"
    if ([string]$VerifyRef.object.sha -ne [string]$Commit.sha) {
        throw "Published evidence ref verification failed."
    }

    return @{
        branch = $BranchName
        commit = [string]$Commit.sha
        base_commit = $BaseCommit
        remote_path = "evidence/phase7_semantic_diagnosis/$RunIdentifier"
        file_count = $Files.Count
    }
}

try {
    $Repo = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null).Trim()
    if ([string]::IsNullOrWhiteSpace($Repo)) {
        throw "This tool must be run from a Git checkout."
    }

    $RepoHead = (& git -C $Repo rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($RepoHead)) {
        throw "Unable to resolve local repository HEAD."
    }

    $Development = Join-Path $Phase3Root "artifacts\numbers3-development-only.csv"
    $Python = Join-Path $SmokeRoot "venv\Scripts\python.exe"
    $Script = Join-Path $PSScriptRoot "semantic_diagnosis.py"
    $Monitor = Join-Path $PSScriptRoot "monitor_semantic_diagnosis.ps1"

    if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
        $OutputRoot = Join-Path $HOME "Downloads"
    }
    $Out = Join-Path $OutputRoot "automlforecast-phase7-semantic-diagnosis-$RunId"
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
    if ($PublishEvidence) { Write-Host "EVIDENCE_BRANCH=$EvidenceBranch" }
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
        Write-Host ""
        Write-Host "Publishing evidence server-side through GitHub Git Data API..."
        $Published = Publish-EvidenceServerSide `
            -RepositoryName $Repository `
            -LocalOutput $Out `
            -RunIdentifier $RunId `
            -BranchName $EvidenceBranch

        $EvidenceCommit = [string]$Published.commit
        Write-Host "EVIDENCE_PUBLISHED=YES" -ForegroundColor Green
        Write-Host "EVIDENCE_BRANCH=$($Published.branch)"
        Write-Host "EVIDENCE_COMMIT=$($Published.commit)"
        Write-Host "EVIDENCE_BASE_COMMIT=$($Published.base_commit)"
        Write-Host "EVIDENCE_PATH=$($Published.remote_path)"
        Write-Host "EVIDENCE_FILE_COUNT=$($Published.file_count)"
    }
    else {
        Write-Host "EVIDENCE_PUBLISHED=NO"
        Write-Host "Local diagnosis evidence remains at: $Out"
        Write-Host "Rerun with -PublishEvidence to create a server-side GitHub evidence branch."
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
    if ($PublishEvidence) { Write-Host "EVIDENCE_BRANCH=$EvidenceBranch" }
}
finally {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "FINAL_LAUNCHER_RC=$FinalRC"
    if ($Log) { Write-Host "LOG=$Log" }
    if ($EvidenceCommit) { Write-Host "EVIDENCE_COMMIT=$EvidenceCommit" }
    Write-Host "PRIMARY_WORKTREE_MUTATED=NO"
    Write-Host "============================================================"
    Write-Host ""
    Read-Host "Enterキーでターミナルに戻ります"
}
