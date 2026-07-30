$ErrorActionPreference = "Stop"
$bytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
$secret = [Convert]::ToBase64String($bytes)
$env:LOTO_SEAL_SECRET = $secret
$env:LOTO_AUTH_DISABLED = "1"
[Environment]::SetEnvironmentVariable("LOTO_SEAL_SECRET", $secret, "User")
[Environment]::SetEnvironmentVariable("LOTO_AUTH_DISABLED", "1", "User")
Write-Host "Secure LOTO_SEAL_SECRET generated and stored for the current user." -ForegroundColor Green
