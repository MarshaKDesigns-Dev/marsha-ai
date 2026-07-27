$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "local_process.ps1")

$root = Get-MarshaRepositoryRoot
$python = Get-MarshaVirtualEnvPython
if (-not (Test-Path -LiteralPath $python)) {
    throw "Repository virtual-environment Python was not found: $python"
}

Write-Host "Repository: $root"
Write-Host "Python: $python"

$existing = Get-MarshaPortListener -Port 5000
if ($existing) {
    Write-Host "Port 5000 is already in use."
    Write-MarshaListener -Listener $existing
    if (-not (Test-MarshaLocalProcess -ProcessInfo $existing)) {
        Write-Warning (
            "Port 5000 belongs to an unrelated process. " +
            "Startup is stopping without terminating it."
        )
        exit 2
    }
    Write-Host "Stopping stale Marsha AI listener."
    [void](Stop-MarshaOwnedListener -Port 5000)
}
else {
    $orphaned = @(Get-MarshaLocalProcesses)
    if ($orphaned) {
        Write-Host "Stopping orphaned Marsha AI Flask process(es)."
        [void](Stop-MarshaLocalProcesses)
    }
}

Write-Host "Applying additive local migrations."
& $python (Join-Path $PSScriptRoot "migrate_local.py")
if ($LASTEXITCODE -ne 0) {
    throw "Local migration runner failed with exit code $LASTEXITCODE."
}

$arguments = @(
    "-m", "flask",
    "--app", "app",
    "run",
    "--no-reload",
    "--host", "127.0.0.1",
    "--port", "5000"
)
$startedAt = Get-Date
$started = Start-Process `
    -FilePath $python `
    -ArgumentList $arguments `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -PassThru

$deadline = (Get-Date).AddSeconds(15)
do {
    Start-Sleep -Milliseconds 250
    $listener = Get-MarshaPortListener -Port 5000
} while (-not $listener -and (Get-Date) -lt $deadline)

if (-not $listener) {
    Stop-Process -Id $started.Id -ErrorAction SilentlyContinue
    throw "Flask did not bind to 127.0.0.1:5000 within 15 seconds."
}
if (-not (Test-MarshaLocalProcess -ProcessInfo $listener)) {
    Stop-Process -Id $started.Id -ErrorAction SilentlyContinue
    throw "The process that acquired port 5000 is not this repository."
}
if ($listener.StartTime -lt $startedAt.AddSeconds(-2)) {
    Stop-Process -Id $listener.ProcessId -ErrorAction SilentlyContinue
    throw "Port 5000 is owned by a listener that predates this startup."
}

Write-Host "Marsha AI local server started successfully."
Write-MarshaListener -Listener $listener
Write-Host "Local URL: http://127.0.0.1:5000"
