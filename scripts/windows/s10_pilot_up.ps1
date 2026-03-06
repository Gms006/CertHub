param(
  [string]$Domain = "certhub.local",
  [string]$IP = "127.0.0.1",
  [switch]$SkipApiCheck,
  [switch]$RunCaddyInCurrentWindow
)

$root = Resolve-Path "$PSScriptRoot/../.."
$frontendDir = Join-Path $root "frontend"
$frontendDist = Join-Path $frontendDir "dist"
$runCaddyScript = Join-Path $PSScriptRoot "s10_run_caddy.ps1"
$setupHostsScript = Join-Path $PSScriptRoot "s10_setup_hosts.ps1"
$trustCaScript = Join-Path $PSScriptRoot "s10_trust_ca.ps1"
$validateScript = Join-Path $PSScriptRoot "s10_validate_tls.ps1"
$portalUrl = "https://$Domain"
$apiHealth = "http://127.0.0.1:8010/health"

Write-Host "==> S10 Piloto LAN: preparando frontend/dist"
if (-not (Test-Path -Path $frontendDist)) {
  Push-Location $frontendDir
  try {
    & npm ci
    if ($LASTEXITCODE -ne 0) {
      throw "Falha no npm ci."
    }

    & npm run build
    if ($LASTEXITCODE -ne 0) {
      throw "Falha no npm run build."
    }
  } finally {
    Pop-Location
  }
} else {
  Write-Host "[OK] frontend/dist já existe."
}

if (-not $SkipApiCheck) {
  Write-Host "==> Validando backend: $apiHealth"
  & curl.exe -sS $apiHealth | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Error "API não respondeu em $apiHealth"
    Write-Host "Inicie o backend com:"
    Write-Host "  cd backend"
    Write-Host "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8010 --env-file .\.env"
    exit 1
  }
  Write-Host "[OK] API respondeu em $apiHealth"
}

Write-Host "==> Atualizando hosts para $Domain"
& $setupHostsScript -Domain $Domain -IP $IP
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host "==> Confiando CA local do Caddy"
& $trustCaScript
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

if ($RunCaddyInCurrentWindow) {
  Write-Host "==> Iniciando Caddy na janela atual (modo bloqueante)"
  & $runCaddyScript
  exit $LASTEXITCODE
}

$hostExe = (Get-Process -Id $PID).Path
Write-Host "==> Iniciando Caddy em nova janela"
Start-Process -FilePath $hostExe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$runCaddyScript`""
) | Out-Null

Start-Sleep -Seconds 2

Write-Host "==> Validando TLS em $portalUrl"
& $validateScript -PortalUrl $portalUrl
exit $LASTEXITCODE
