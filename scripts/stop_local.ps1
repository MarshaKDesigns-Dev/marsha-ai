$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "local_process.ps1")

$root = Get-MarshaRepositoryRoot
Write-Host "Repository: $root"

$listener = Get-MarshaPortListener -Port 5000
if (-not $listener) {
    $orphaned = @(Get-MarshaLocalProcesses)
    if ($orphaned) {
        Write-Host (
            "Port 5000 is free, but repository-owned Marsha AI process(es) " +
            "remain."
        )
        [void](Stop-MarshaLocalProcesses)
    }
    Write-Host "Port 5000 is free and no Marsha AI processes remain."
    exit 0
}

Write-MarshaListener -Listener $listener
if (-not (Test-MarshaLocalProcess -ProcessInfo $listener)) {
    Write-Warning (
        "Port 5000 belongs to an unrelated process. " +
        "No process was stopped."
    )
    exit 2
}

[void](Stop-MarshaOwnedListener -Port 5000)
if (Get-MarshaPortListener -Port 5000) {
    throw "Port 5000 is still occupied."
}
if (@(Get-MarshaLocalProcesses)) {
    throw "A repository-owned Marsha AI process is still running."
}
Write-Host (
    "Marsha AI stopped. Port 5000 is free and no repository-owned Flask " +
    "processes remain."
)
