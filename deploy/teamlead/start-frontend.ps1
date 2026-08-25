Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$frontendRoot = Join-Path $repoRoot 'frontend'

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'npm was not found. Install Node.js 22 LTS first.'
}

Push-Location $frontendRoot
try {
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
        & npm ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci exited with code $LASTEXITCODE."
        }
    }
    & npm run dev
    if ($LASTEXITCODE -ne 0) {
        throw "npm run dev exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
