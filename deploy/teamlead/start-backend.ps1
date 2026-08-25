Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $repoRoot 'backend\.env'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing $python. Create the repository virtual environment first."
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Missing $envFile. Copy deploy\teamlead\backend.env.example to backend\.env and fill it locally."
}

Push-Location $repoRoot
try {
    & $python 'backend\run.py'
    if ($LASTEXITCODE -ne 0) {
        throw "Backend exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
