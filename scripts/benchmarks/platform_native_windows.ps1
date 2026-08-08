param(
    [string]$TargetSha = "f13ebf6dd4b5495eb0bd47f27375c7e47c17ce60",
    [int]$TargetPr = 183
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Repo = "arumajirou/loto_forecast_platform"
$TargetBranch = "fix/windows-portability-verification-v1"
$ExpectedBase = "f5f5c5e1feb97042fe9a3c947a9a97aac2281dac"
$ExpectedMain = "5926ad6d00314c7ba5ec7133bb377dd5beb1316c"

$RepoRoot = (git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not $RepoRoot) {
    throw "Run inside the benchmark repository checkout."
}

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$RunId = "platform-bench-windows-native-$Stamp"
$RelOut = "benchmark-results/$RunId"
$Out = Join-Path $RepoRoot $RelOut
$Target = Join-Path $env:TEMP "loto-target-$PID"
$Phase = "startup"

New-Item -ItemType Directory -Force -Path $Out | Out-Null

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$File,
        [Parameter()][string[]]$ArgumentList = @()
    )

    & $File @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$File exited with $LASTEXITCODE"
    }
}

function Write-JsonAtomic {
    param(
        [Parameter(Mandatory)]$Object,
        [Parameter(Mandatory)][string]$Path,
        [int]$Depth = 8
    )

    $tmp = "$Path.tmp-$PID"
    $Object | ConvertTo-Json -Depth $Depth | Set-Content -Encoding utf8 $tmp
    Move-Item -Force $tmp $Path
}

function Get-SystemSample {
    $os = Get-CimInstance Win32_OperatingSystem
    $processor = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -ErrorAction SilentlyContinue |
        Where-Object Name -eq "_Total" |
        Select-Object -First 1
    $disk = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -ErrorAction SilentlyContinue |
        Where-Object Name -eq "_Total" |
        Select-Object -First 1

    [pscustomobject]@{
        timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
        free_memory_mb = [math]::Round([double]$os.FreePhysicalMemory / 1024, 1)
        system_cpu_pct = if ($processor) { [double]$processor.PercentProcessorTime } else { $null }
        disk_bytes_per_sec = if ($disk) { [double]$disk.DiskBytesPersec } else { $null }
        disk_read_bytes_per_sec = if ($disk) { [double]$disk.DiskReadBytesPersec } else { $null }
        disk_write_bytes_per_sec = if ($disk) { [double]$disk.DiskWriteBytesPersec } else { $null }
    }
}

$Metrics = [System.Collections.Generic.List[object]]::new()

function Measure-Stage {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Body
    )

    Write-Host "BENCH_STAGE=$Name"
    $before = Get-SystemSample
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $ok = $true

    try {
        & $Body
    }
    catch {
        $ok = $false
        throw
    }
    finally {
        $sw.Stop()
        $after = Get-SystemSample
        $Metrics.Add([pscustomobject]@{
            stage = $Name
            wall_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)
            free_memory_mb_before = $before.free_memory_mb
            free_memory_mb_after = $after.free_memory_mb
            system_cpu_pct_before = $before.system_cpu_pct
            system_cpu_pct_after = $after.system_cpu_pct
            disk_bytes_per_sec_before = $before.disk_bytes_per_sec
            disk_bytes_per_sec_after = $after.disk_bytes_per_sec
            success = $ok
        })
    }
}

try {
    $Phase = "capability"
    foreach ($cmd in @("gh", "git", "uv")) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
            throw "Missing tool: $cmd"
        }
    }
    if ($env:WSL_DISTRO_NAME) {
        throw "WSL detected; Native Windows required."
    }

    $Phase = "remote_guard"
    $pr = gh api "repos/$Repo/pulls/$TargetPr" | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Failed to read PR #$TargetPr" }
    $main = gh api "repos/$Repo/git/ref/heads/main" | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Failed to read main ref" }

    if ($pr.head.sha -ne $TargetSha) { throw "PR head moved: $($pr.head.sha)" }
    if ($pr.base.sha -ne $ExpectedBase) { throw "PR base moved: $($pr.base.sha)" }
    if ($main.object.sha -ne $ExpectedMain) { throw "main moved: $($main.object.sha)" }
    if (-not $pr.draft) { throw "PR #$TargetPr must remain Draft." }

    $Phase = "platform"
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $cs = Get-CimInstance Win32_ComputerSystem
    $gpu = "NOT_AVAILABLE"
    $gpuDriver = $null
    $cudaReported = $null

    if (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue) {
        try {
            $gpuLine = (& nvidia-smi.exe --query-gpu=name,driver_version --format=csv,noheader | Select-Object -First 1)
            if ($gpuLine) {
                $parts = $gpuLine -split ","
                $gpu = $parts[0].Trim()
                $gpuDriver = $parts[1].Trim()
            }
            $smiHeader = (& nvidia-smi.exe | Select-Object -First 3) -join " "
            if ($smiHeader -match "CUDA Version:\s*([0-9.]+)") { $cudaReported = $Matches[1] }
        }
        catch {}
    }

    $deviceGuard = $null
    try {
        $deviceGuard = Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard
    }
    catch {}

    Write-JsonAtomic -Object ([pscustomobject]@{
        run_id = $RunId
        platform = "Native Windows"
        os = $os.Caption
        os_version = $os.Version
        build = $os.BuildNumber
        cpu = $cpu.Name.Trim()
        cores = $cpu.NumberOfCores
        logical_processors = $cs.NumberOfLogicalProcessors
        total_memory_gb = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
        hypervisor_present = $cs.HypervisorPresent
        vbs_status = if ($deviceGuard) { $deviceGuard.VirtualizationBasedSecurityStatus } else { $null }
        gpu = $gpu
        gpu_driver = $gpuDriver
        cuda_reported_by_driver = $cudaReported
        powershell = $PSVersionTable.PSVersion.ToString()
        uv = (uv --version)
        git = (git --version)
        target_pr = $TargetPr
        target_sha = $TargetSha
        base_sha = $ExpectedBase
        main_sha = $ExpectedMain
    }) -Path (Join-Path $Out "platform.json")

    $Phase = "target_fetch"
    Invoke-Native -File "git" -ArgumentList @(
        "-C", $RepoRoot, "fetch", "--no-tags", "origin",
        "+refs/heads/$TargetBranch`:refs/remotes/origin/$TargetBranch"
    )

    $fetchedTarget = (git -C $RepoRoot rev-parse "refs/remotes/origin/$TargetBranch").Trim()
    if ($LASTEXITCODE -ne 0 -or $fetchedTarget -ne $TargetSha) {
        throw "Fetched target branch does not match expected PR head."
    }

    if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
    Invoke-Native -File "git" -ArgumentList @("-C", $RepoRoot, "worktree", "add", "--detach", $Target, $TargetSha)
    if ((git -C $Target rev-parse HEAD).Trim() -ne $TargetSha) {
        throw "Target checkout mismatch."
    }

    $Phase = "python"
    Measure-Stage -Name "uv_python_312_ready" -Body {
        Invoke-Native -File "uv" -ArgumentList @("python", "install", "3.12.13")
    }
    $py = (uv python find 3.12.13).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $py)) { throw "Python 3.12.13 unavailable." }

    $Phase = "lock"
    Measure-Stage -Name "uv_lock_check" -Body {
        Push-Location $Target
        try { Invoke-Native -File "uv" -ArgumentList @("lock", "--check") }
        finally { Pop-Location }
    }

    $Phase = "resolve"
    Measure-Stage -Name "windows_resolve_first" -Body {
        Push-Location $Target
        try { Invoke-Native -File "uv" -ArgumentList @("sync", "--dry-run", "--locked", "--python", "3.12.13") }
        finally { Pop-Location }
    }
    Measure-Stage -Name "windows_resolve_second" -Body {
        Push-Location $Target
        try { Invoke-Native -File "uv" -ArgumentList @("sync", "--dry-run", "--locked", "--python", "3.12.13") }
        finally { Pop-Location }
    }

    $Phase = "dependency_tree"
    $tree = Join-Path $Out "windows-tree.txt"
    Measure-Stage -Name "windows_dependency_tree" -Body {
        Push-Location $Target
        try {
            & uv tree --locked --python-version 3.12 --python-platform x86_64-pc-windows-msvc |
                Tee-Object -FilePath $tree
            if ($LASTEXITCODE -ne 0) { throw "uv tree failed" }
        }
        finally { Pop-Location }
    }
    if (Select-String -Path $tree -Pattern '(?i)\btriton\b') {
        throw "Triton selected on Native Windows."
    }

    $Phase = "compile"
    Measure-Stage -Name "python_compile_src" -Body {
        Push-Location $Target
        try { Invoke-Native -File $py -ArgumentList @("-m", "compileall", "-q", "src") }
        finally { Pop-Location }
    }

    $Phase = "wheel"
    $dist = Join-Path $Target ".benchmark-dist"
    New-Item -ItemType Directory -Force -Path $dist | Out-Null
    Measure-Stage -Name "wheel_build" -Body {
        Push-Location $Target
        try { Invoke-Native -File "uv" -ArgumentList @("build", "--wheel", "--out-dir", $dist) }
        finally { Pop-Location }
    }
    $wheel = Get-ChildItem $dist -Filter "*.whl" | Select-Object -First 1
    if (-not $wheel) { throw "Wheel not produced." }

    $Phase = "wheel_import"
    $venv = Join-Path $Target ".venv-portability-bench"
    Measure-Stage -Name "wheel_install_import_312" -Body {
        Push-Location $Target
        try {
            Invoke-Native -File "uv" -ArgumentList @("venv", $venv, "--python", "3.12.13")
            $venvPy = Join-Path $venv "Scripts\python.exe"
            Invoke-Native -File "uv" -ArgumentList @("pip", "install", "--python", $venvPy, "--no-deps", $wheel.FullName)
            Invoke-Native -File $venvPy -ArgumentList @("-c", "import loto; print('loto_version=' + loto.__version__)")
        }
        finally { Pop-Location }
    }

    $Phase = "results"
    $Metrics | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $Out "metrics.csv")
    $allPass = (@($Metrics | Where-Object success -ne $true).Count -eq 0)
    if (-not $allPass) { throw "At least one measured stage failed." }

    Write-JsonAtomic -Object ([pscustomobject]@{
        run_id = $RunId
        platform = "Native Windows"
        target_sha = $TargetSha
        target_pr = $TargetPr
        triton_selected = $false
        all_stages_pass = $true
        stages = $Metrics
    }) -Path (Join-Path $Out "summary.json")

    Write-JsonAtomic -Object ([pscustomobject]@{
        run_id = $RunId
        overall_status = "PASS"
        phase = "complete"
        valid_for_performance_comparison = $true
        target_sha = $TargetSha
    }) -Path (Join-Path $Out "status.json")

    Write-Host "WINDOWS_TRITON_SELECTED=false"
    Write-Host "WINDOWS_LOCAL_BENCHMARK=PASS"
    Write-Host "RUN_ID=$RunId"
    Write-Host "OUTPUT=$RelOut"
    Write-Host "TARGET_SHA=$TargetSha"
}
catch {
    $message = $_.Exception.Message
    $Metrics | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $Out "metrics.csv")
    Write-JsonAtomic -Object ([pscustomobject]@{
        run_id = $RunId
        overall_status = "FAILED"
        phase = $Phase
        error = $message
        valid_for_performance_comparison = $false
        target_sha = $TargetSha
    }) -Path (Join-Path $Out "status.json")
    Write-Host "WINDOWS_LOCAL_BENCHMARK=FAIL"
    Write-Host "FAILED_PHASE=$Phase"
    Write-Host "ERROR=$message"
    Write-Host "OUTPUT=$RelOut"
    throw
}
finally {
    if (Test-Path $Target) {
        git -C $RepoRoot worktree remove --force $Target 2>$null | Out-Null
    }
}
