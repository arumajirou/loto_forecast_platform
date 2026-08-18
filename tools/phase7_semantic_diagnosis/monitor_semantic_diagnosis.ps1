param(
    [Parameter(Mandatory=$true)]
    [string]$Root
)

$ErrorActionPreference = "SilentlyContinue"
$Started = Get-Date

function Read-SharedText([string]$Path) {
    try {
        $Mode = [System.IO.FileMode]::Open
        $Access = [System.IO.FileAccess]::Read
        $Share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
        $Stream = New-Object System.IO.FileStream($Path, $Mode, $Access, $Share)
        try {
            $Reader = New-Object System.IO.StreamReader($Stream, [System.Text.Encoding]::UTF8, $true)
            try { return $Reader.ReadToEnd() } finally { $Reader.Dispose() }
        }
        finally { $Stream.Dispose() }
    }
    catch { return $null }
}

while ($true) {
    Clear-Host
    Write-Host "============================================================"
    Write-Host " Phase 7 Semantic Diagnosis Monitor"
    Write-Host "============================================================"
    Write-Host "ROOT=$Root"
    Write-Host ("ELAPSED=" + ((Get-Date) - $Started).ToString())

    $ProgressPath = Join-Path $Root "DIAGNOSIS_PROGRESS.json"
    $Text = Read-SharedText $ProgressPath
    if ($null -ne $Text -and -not [string]::IsNullOrWhiteSpace($Text)) {
        try {
            $P = $Text | ConvertFrom-Json
            Write-Host ("PHASE=" + $P.phase)
            Write-Host ("PROGRESS=" + $P.progress_percent + "%")
            Write-Host ("CURRENT_SEED=" + $P.current_seed)
            Write-Host ("COMPLETED=" + $P.completed + "/" + $P.total)
            Write-Host ("STATUS=" + $P.status)
            Write-Host ("PID=" + $P.pid)
            if ($P.phase -eq "COMPLETE") { break }
        }
        catch {
            Write-Host "PROGRESS=temporarily unreadable (atomic replace)"
        }
    }
    else {
        Write-Host "PHASE=STARTING"
        Write-Host "PROGRESS=0%"
        Write-Host "CURRENT_SEED=1"
        Write-Host "COMPLETED=0/20"
        Write-Host "STATUS=STARTING"
    }

    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "MONITOR=COMPLETE"
Read-Host "Press Enter to return to the terminal"
