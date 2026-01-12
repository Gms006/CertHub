$root = Resolve-Path "$PSScriptRoot/../.."
$caddyDir = Join-Path $root "infra/https"
$caddyfile = Join-Path $caddyDir "Caddyfile"

Push-Location $caddyDir
try {
  caddy run --config $caddyfile --adapter caddyfile
} finally {
  Pop-Location
}
