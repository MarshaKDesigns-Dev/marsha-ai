Set-StrictMode -Version Latest

function Get-MarshaRepositoryRoot {
    return [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot "..")
    )
}

function Get-MarshaVirtualEnvPython {
    $root = Get-MarshaRepositoryRoot
    return [System.IO.Path]::GetFullPath(
        (Join-Path $root "venv\Scripts\python.exe")
    )
}

function Get-MarshaProcessInfo {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $process = Get-CimInstance Win32_Process `
        -Filter "ProcessId = $ProcessId" `
        -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }
    $processInfo = Get-Process `
        -Id $ProcessId `
        -ErrorAction SilentlyContinue
    if (-not $processInfo) {
        return $null
    }
    return [PSCustomObject]@{
        ProcessId = [int]$process.ProcessId
        ParentProcessId = [int]$process.ParentProcessId
        StartTime = $processInfo.StartTime
        ExecutablePath = [string]$process.ExecutablePath
        CommandLine = [string]$process.CommandLine
    }
}

function Get-MarshaPortListener {
    param([int]$Port = 5000)

    $listener = Get-NetTCPConnection `
        -LocalPort $Port `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return $null
    }

    return Get-MarshaProcessInfo -ProcessId $listener.OwningProcess
}

function Test-MarshaLocalProcess {
    param(
        [Parameter(Mandatory = $true)]$ProcessInfo,
        [string]$RepositoryRoot = (Get-MarshaRepositoryRoot),
        [string]$VirtualEnvPython = (Get-MarshaVirtualEnvPython)
    )

    $command = ([string]$ProcessInfo.CommandLine).ToLowerInvariant()
    $executable = ([string]$ProcessInfo.ExecutablePath).ToLowerInvariant()
    $root = $RepositoryRoot.ToLowerInvariant()
    $python = $VirtualEnvPython.ToLowerInvariant()
    $isPython = $executable.EndsWith("python.exe")
    $usesRepository = (
        $command.Contains($python) -or
        $command.Contains($root)
    )
    $isFlask = (
        ($command.Contains("-m flask") -and $command.Contains("--app app")) -or
        $command.Contains((Join-Path $root "app.py")) -or
        $command.EndsWith(" app.py")
    )
    $isWorker = $command.Contains(
        "-m services.sponsorship_intelligence_worker"
    )
    return (
        $isPython -and
        $usesRepository -and
        ($isFlask -or $isWorker)
    )
}

function Write-MarshaListener {
    param([Parameter(Mandatory = $true)]$Listener)

    Write-Host "Listener PID: $($Listener.ProcessId)"
    Write-Host "Listener start time: $($Listener.StartTime)"
    Write-Host "Listener executable: $($Listener.ExecutablePath)"
}

function Get-MarshaLocalProcesses {
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    foreach ($process in $processes) {
        $candidate = [PSCustomObject]@{
            ProcessId = [int]$process.ProcessId
            ParentProcessId = [int]$process.ParentProcessId
            StartTime = $null
            ExecutablePath = [string]$process.ExecutablePath
            CommandLine = [string]$process.CommandLine
        }
        if (Test-MarshaLocalProcess -ProcessInfo $candidate) {
            $processInfo = Get-MarshaProcessInfo `
                -ProcessId $candidate.ProcessId
            if ($processInfo) {
                $processInfo
            }
        }
    }
}

function Stop-MarshaLocalProcesses {
    param([int]$TimeoutSeconds = 10)

    $owned = @(Get-MarshaLocalProcesses)
    if (-not $owned) {
        return 0
    }

    foreach ($processInfo in $owned) {
        Write-Host (
            "Stopping Marsha AI process PID $($processInfo.ProcessId) " +
            "(parent $($processInfo.ParentProcessId))."
        )
        Stop-Process `
            -Id $processInfo.ProcessId `
            -ErrorAction SilentlyContinue
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 200
        $remaining = @(Get-MarshaLocalProcesses)
    } while ($remaining -and (Get-Date) -lt $deadline)
    if ($remaining) {
        $remainingIds = ($remaining.ProcessId -join ", ")
        throw (
            "Repository-owned Marsha AI processes did not stop: " +
            $remainingIds
        )
    }
    return $owned.Count
}

function Stop-MarshaOwnedListener {
    param(
        [int]$Port = 5000,
        [int]$TimeoutSeconds = 10
    )

    $listener = Get-MarshaPortListener -Port $Port
    if (-not $listener) {
        return $false
    }
    Write-MarshaListener -Listener $listener
    if (-not (Test-MarshaLocalProcess -ProcessInfo $listener)) {
        throw (
            "Port $Port is owned by an unrelated process. " +
            "It will not be stopped automatically."
        )
    }

    [void](Stop-MarshaLocalProcesses -TimeoutSeconds $TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 200
        $remaining = Get-MarshaPortListener -Port $Port
    } while ($remaining -and (Get-Date) -lt $deadline)
    if ($remaining) {
        throw "The Marsha AI listener did not release port $Port."
    }
    return $true
}
