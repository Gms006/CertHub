param(
  [string]$PortalUrl = "https://portal.local"
)

$apiHealth = "$PortalUrl/api/v1/health"

Write-Host "==> HEAD portal: $PortalUrl"
$portalHeaders = curl.exe -k -I $PortalUrl 2>$null
$portalHeaders

Write-Host "==> HEAD API health: $apiHealth"
$apiHeaders = curl.exe -k -I $apiHealth 2>$null
$apiHeaders

$requiredHeaders = @(
  "Strict-Transport-Security",
  "X-Content-Type-Options",
  "X-Frame-Options",
  "Content-Security-Policy"
)

Write-Host "==> Checking security headers on portal response"
foreach ($header in $requiredHeaders) {
  if ($portalHeaders -match $header) {
    Write-Host "[OK] $header"
  } else {
    Write-Warning "[MISSING] $header"
  }
}

Write-Host "==> Note: remove -k after trusting the Caddy root CA (caddy trust)."
