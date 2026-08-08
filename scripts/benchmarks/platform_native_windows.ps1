param(
    [string]$TargetSha = "f13ebf6dd4b5495eb0bd47f27375c7e47c17ce60",
    [int]$TargetPr = 183
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Repo = "arumajirou/loto_forecast_platform"
$ExpectedBase = "f5f5c5e1feb97042fe9a3c947a9a97aac2281dac"
$ExpectedMain = "5926ad6d00314c7ba5ec7133bb377dd5beb1316c"

$RepoRoot = (git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw "Run inside the benchmark repository checkout." }

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$RunId = "platform-bench-windows-native-$Stamp"
$RelOut = "benchmark-results/$RunId"
$Out = Join-Path $RepoRoot $RelOut
$Target = Join-Path $env:TEMP "loto-target-$PID"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

function Invoke-Native([string]$File, [string[]]$Args) {
    & $File @Args
    if ($LASTEXITCODE -ne 0) { throw "$File exited with $LASTEXITCODE" }
}

$Metrics = @()
function Measure-Stage([string]$Name, [scriptblock]$Body) {
    $before = Get-CimInstance Win32_OperatingSystem
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $ok = $true
    try { & $Body }
    catch { $ok = $false; throw }
    finally {
        $sw.Stop()
        $after = Get-CimInstance Win32_OperatingSystem
        $script:Metrics += [pscustomobject]@{
            stage = $Name
            wall_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)
            free_memory_mb_before = [math]::Round([double]$before.FreePhysicalMemory / 1024, 1)
            free_memory_mb_after = [math]::Round([double]$after.FreePhysicalMemory / 1024, 1)
            success = $ok
        }
    }
}

try {
    foreach ($cmd in @("gh","git","uv")) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Missing tool: $cmd" }
    }
    if ($env:WSL_DISTRO_NAME) { throw "WSL detected; Native Windows required." }

    $pr = gh api "repos/$Repo/pulls/$TargetPr" | ConvertFrom-Json
    $main = gh api "repos/$Repo/git/ref/heads/main" | ConvertFrom-Json
    if ($pr.head.sha -ne $TargetSha) { throw "PR head moved: $($pr.head.sha)" }
    if ($pr.base.sha -ne $ExpectedBase) { throw "PR base moved: $($pr.base.sha)" }
    if ($main.object.sha -ne $ExpectedMain) { throw "main moved: $($main.object.sha)" }
    if (-not $pr.draft) { throw "PR #$TargetPr must remain Draft." }

    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $cs = Get-CimInstance Win32_ComputerSystem
    $gpu = "NOT_AVAILABLE"
    if (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue) {
        try { $gpu = (& nvidia-smi.exe --query-gpu=name --format=csv,noheader | Select-Object -First 1).Trim() } catch {}
    }

    [pscustomobject]@{
        run_id = $RunId
        platform = "Native Windows"
        os = $os.Caption
        os_version = $os.Version
        build = $os.BuildNumber
        cpu = $cpu.Name
        logical_processors = $cs.NumberOfLogicalProcessors
        total_memory_gb = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
        gpu = $gpu
        powershell = $PSVersionTable.PSVersion.ToString()
        uv = (uv --version)
        git = (git --version)
        target_pr = $TargetPr
        target_sha = $TargetSha
        base_sha = $ExpectedBase
        main_sha = $ExpectedMain
    } | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $Out "platform.json")

    Invoke-Native git @("-C",$RepoRoot,"fetch","--no-tags","origin",$TargetSha)
    if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
    Invoke-Native git @("-C",$RepoRoot,"worktree","add","--detach",$Target,$TargetSha)
    if ((git -C $Target rev-parse HEAD).Trim() -ne $TargetSha) { throw "Target checkout mismatch." }

    Measure-Stage "uv_python_312_ready" {
        Invoke-Native uv @("python","install","3.12.13")
    }
    $py = (uv python find 3.12.13).Trim()

    Measure-Stage "uv_lock_check" {
        Push-Location $Target
        try { Invoke-Native uv @("lock","--check") } finally { Pop-Location }
    }

    Measure-Stage "windows_resolve_first" {
        Push-Location $Target
        try { Invoke-Native uv @("sync","--dry-run","--locked","--python","3.12.13") } finally { Pop-Location }
    }
    Measure-Stage "windows_resolve_second" {
        Push-Location $Target
        try { Invoke-Native uv @("sync","--dry-run","--locked","--python","3.12.13") } finally { Pop-Location }
    }

    $tree = Join-Path $Out "windows-tree.txt"
    Measure-Stage "windows_dependency_tree" {
        Push-Location $Target
        try {
            & uv tree --locked --python-version 3.12 --python-platform x86_64-pc-windows-msvc |
                Tee-Object -FilePath $tree
            if ($LASTEXITCODE -ne 0) { throw "uv tree failed" }
        } finally { Pop-Location }
    }
    if (Select-String -Path $tree -Pattern '(?i)\btriton\b') { throw "Triton selected on Native Windows." }

    Measure-Stage "python_compile_src" {
        Push-Location $Target
        try { Invoke-Native $py @("-m","compileall","-q","src") } finally { Pop-Location }
    }

    $dist = Join-Path $Out "dist"
    New-Item -ItemType Directory -Force -Path $dist | Out-Null
    Measure-Stage "wheel_build" {
        Push-Location $Target
        try { Invoke-Native uv @("build","--wheel","--out-dir",$dist) } finally { Pop-Location }
    }
    $wheel = Get-ChildItem $dist -Filter "*.whl" | Select-Object -First 1
    if (-not $wheel) { throw "Wheel not produced." }

    $venv = Join-Path $Target ".venv-portability-bench"
    Measure-Stage "wheel_install_import_312" {
        Push-Location $Target
        try {
            Invoke-Native uv @("venv",$venv,"--python","3.12.13")
            $venvPy = Join-Path $venv "Scripts\python.exe"
            Invoke-Native uv @("pip","install","--python",$venvPy,"--no-deps",$wheel.FullName)
            Invoke-Native $venvPy @("-c","import loto; print('loto_version=' + loto.__version__)")
        } finally { Pop-Location }
    }

    $Metrics | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $Out "metrics.csv")
    [pscustomobject]@{
        run_id = $RunId
        platform = "Native Windows"
        target_sha = $TargetSha
        target_pr = $TargetPr
        triton_selected = $false
        all_stages_pass = (@($Metrics | Where-Object success -ne $true).Count -eq 0)
        stages = $Metrics
    } | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $Out "summary.json")

    Write-Host "WINDOWS_TRITON_SELECTED=false"
    Write-Host "WINDOWS_LOCAL_BENCHMARK=PASS"
    Write-Host "RUN_ID=$RunId"
    Write-Host "OUTPUT=$RelOut"
    Write-Host "TARGET_SHA=$TargetSha"
}
finally {
    if (Test-Path $Target) {
        git -C $RepoRoot worktree remove --force $Target 2>$null | Out-Null
    }
}
