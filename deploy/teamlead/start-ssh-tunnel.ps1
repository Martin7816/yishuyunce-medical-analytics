Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$configPath = Join-Path $PSScriptRoot 'ssh-tunnel.config.ps1'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Missing $configPath. Copy ssh-tunnel.config.ps1.example and fill it locally."
}

. $configPath

foreach ($name in 'SshUser', 'SshHost', 'IdentityFile') {
    $value = Get-Variable -Name $name -ValueOnly -ErrorAction SilentlyContinue
    if (-not $value -or $value -like '<*>' ) {
        throw "$name is not configured in ssh-tunnel.config.ps1."
    }
}
if (-not (Test-Path -LiteralPath $IdentityFile)) {
    throw "SSH identity file does not exist: $IdentityFile"
}

$forward = "${LocalPort}:${RemoteHost}:${RemotePort}"
Write-Host "Starting read-only SSH port forward on 127.0.0.1:$LocalPort"
Write-Host "Press Ctrl+C to stop the tunnel."
& ssh -N -T -o ExitOnForwardFailure=yes -i $IdentityFile -L $forward "$SshUser@$SshHost"
if ($LASTEXITCODE -ne 0) {
    throw "SSH tunnel exited with code $LASTEXITCODE."
}
