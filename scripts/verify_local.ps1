$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot "local_process.ps1")

$root = Get-MarshaRepositoryRoot
$python = Get-MarshaVirtualEnvPython
Write-Host "Repository: $root"
Write-Host "Python: $python"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Repository virtual-environment Python was not found."
}

$listener = Get-MarshaPortListener -Port 5000
if (-not $listener) {
    throw "No process is listening on port 5000."
}
Write-MarshaListener -Listener $listener
if (-not (Test-MarshaLocalProcess -ProcessInfo $listener)) {
    throw "The port-5000 listener is not owned by this repository."
}

try {
    $env:MARSHA_SKIP_CREATE_ALL = "1"
    & $python (Join-Path $PSScriptRoot "verify_local.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Local application verification failed."
    }
}
finally {
    Remove-Item Env:MARSHA_SKIP_CREATE_ALL -ErrorAction SilentlyContinue
}
Write-Host "Local environment verification passed."
