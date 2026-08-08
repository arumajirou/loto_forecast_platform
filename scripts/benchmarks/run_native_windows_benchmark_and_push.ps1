param(
    [string]$Branch = "bench/platform-comparison-20260808-v1",
    [string]$TargetSha = "f13ebf6dd4b5495eb0bd47f27375c7e47c17ce60",
    [int]$TargetPr = 183
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Repo = "arumajirou/loto_forecast_platform"
$RepoRoot = (git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not $RepoRoot) { throw "Run inside the repository checkout." }

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$File,
        [Parameter()][string[]]$ArgumentList = @()
    )
    & $File @ArgumentList
    if ($LASTEXITCODE -ne 0) { throw "$File exited with $LASTEXITCODE" }
}

Write-Host "=== Native Windows benchmark: pull -> run -> verify -> push ==="

if ($env:WSL_DISTRO_NAME) { throw "WSL detected; Native Windows required." }

Invoke-Native -File "git" -ArgumentList @("-C", $RepoRoot, "fetch", "origin", $Branch)
Invoke-Native -File "git" -ArgumentList @("-C", $RepoRoot, "switch", $Branch)
Invoke-Native -File "git" -ArgumentList @("-C", $RepoRoot, "pull", "--ff-only", "origin", $Branch)

$InitialHead = (git -C $RepoRoot rev-parse HEAD).Trim()
$RemoteLine = git -C $RepoRoot ls-remote origin "refs/heads/$Branch"
$RemoteHead = ($RemoteLine -split "\s+")[0]
if ($InitialHead -ne $RemoteHead) { throw "Local/remote benchmark branch mismatch after pull." }

$scriptPath = Join-Path $RepoRoot "scripts\benchmarks\platform_native_windows.ps1"
if (-not (Test-Path $scriptPath)) { throw "Benchmark harness missing: $scriptPath" }

$Before = @(
    Get-ChildItem (Join-Path $RepoRoot "benchmark-results") -Directory -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
)

Write-Host "GITHUB_TO_WINDOWS_PULL=PASS"
Write-Host "HARNESS_HEAD=$InitialHead"

$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
& $pwsh -NoProfile -File $scriptPath -TargetSha $TargetSha -TargetPr $TargetPr
if ($LASTEXITCODE -ne 0) {
    Write-Host "WINDOWS_BENCHMARK_EXECUTION=FAIL"
    throw "Native Windows benchmark exited with $LASTEXITCODE. No result commit/push will occur."
}

$After = @(
    Get-ChildItem (Join-Path $RepoRoot "benchmark-results") -Directory -ErrorAction Stop |
        Select-Object -ExpandProperty FullName
)
$NewDirs = @($After | Where-Object { $_ -notin $Before })
if ($NewDirs.Count -ne 1) { throw "Expected exactly one new benchmark result directory; found $($NewDirs.Count)." }

$ResultDir = $NewDirs[0]
$statusPath = Join-Path $ResultDir "status.json"
$summaryPath = Join-Path $ResultDir "summary.json"
$metricsPath = Join-Path $ResultDir "metrics.csv"

foreach ($required in @($statusPath, $summaryPath, $metricsPath)) {
    if (-not (Test-Path $required)) { throw "Required successful result file missing: $required" }
}

$status = Get-Content $statusPath -Raw | ConvertFrom-Json
$summary = Get-Content $summaryPath -Raw | ConvertFrom-Json
if ($status.overall_status -ne "PASS") { throw "Result status is not PASS." }
if (-not $status.valid_for_performance_comparison) { throw "Result is not valid for performance comparison." }
if ($status.target_sha -ne $TargetSha) { throw "Result target SHA mismatch." }
if (-not $summary.all_stages_pass) { throw "Summary reports failed stage(s)." }
if ($summary.target_sha -ne $TargetSha) { throw "Summary target SHA mismatch." }
if ($summary.triton_selected) { throw "Triton unexpectedly selected on Native Windows." }

$changes = @(git -C $RepoRoot status --porcelain=v1)
$bad = @($changes | Where-Object {
    $_ -and ($_ -notmatch 'benchmark-results[/\\]platform-bench-windows-native-')
})
if ($bad.Count -gt 0) {
    Write-Host "UNEXPECTED_CHANGE=$($bad -join ';')"
    throw "Files outside the new benchmark result directory changed; refusing to commit."
}

$RemoteBeforeLine = git -C $RepoRoot ls-remote origin "refs/heads/$Branch"
$RemoteBefore = ($RemoteBeforeLine -split "\s+")[0]
if ($RemoteBefore -ne $InitialHead) { throw "Remote benchmark branch moved during execution; refusing to push." }

$relResult = [IO.Path]::GetRelativePath($RepoRoot, $ResultDir)
Invoke-Native -File "git" -ArgumentList @("-C", $RepoRoot, "add", "--", $relResult)

$staged = @(git -C $RepoRoot diff --cached --name-only)
if ($staged.Count -eq 0) { throw "No benchmark result files staged." }
$badStaged = @($staged | Where-Object { $_ -notmatch '^benchmark-results/' })
if ($badStaged.Count -gt 0) { throw "Unexpected staged files; refusing to commit." }

Invoke-Native -File "git" -ArgumentList @("-C", $RepoRoot, "commit", "-m", "chore(bench): record successful Native Windows benchmark")
$ResultCommit = (git -C $RepoRoot rev-parse HEAD).Trim()
Invoke-Native -File "git" -ArgumentList @("-C", $RepoRoot, "push", "origin", $Branch)

$RemoteAfterLine = git -C $RepoRoot ls-remote origin "refs/heads/$Branch"
$RemoteAfter = ($RemoteAfterLine -split "\s+")[0]
if ($RemoteAfter -ne $ResultCommit) { throw "Remote result SHA mismatch after push." }

$pr = gh pr view 192 --repo $Repo --json isDraft,headRefOid,url | ConvertFrom-Json
if (-not $pr.isDraft) { throw "PR #192 unexpectedly left Draft state." }
if ($pr.headRefOid -ne $ResultCommit) { throw "PR #192 head does not match pushed result commit." }

Write-Host "WINDOWS_BENCHMARK_EXECUTION=PASS"
Write-Host "RESULT_STATUS=PASS"
Write-Host "WINDOWS_RESULT_PUSH=PASS"
Write-Host "REMOTE_HEAD_VERIFY=PASS"
Write-Host "PR_192_REMOTE_UPDATE=PASS"
Write-Host "RESULT_COMMIT=$ResultCommit"
Write-Host "RESULT_DIR=$relResult"
Write-Host "NEXT_TARGET=WINDOWS_RESULT_AUDIT"
Write-Host "STOP_REASON=NONE"
