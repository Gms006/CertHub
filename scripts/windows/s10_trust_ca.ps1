$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Error "Este script precisa ser executado como Administrador."
  exit 1
}

$caddyCommand = Get-Command caddy -ErrorAction SilentlyContinue
if (-not $caddyCommand) {
  Write-Error "Comando 'caddy' não encontrado no PATH. Instale o Caddy e tente novamente."
  Write-Host "Sugestão: choco install caddy ou use o binário oficial no PATH."
  exit 1
}

Write-Host "==> Executando caddy trust"
& caddy trust
if ($LASTEXITCODE -ne 0) {
  Write-Error "Falha ao executar 'caddy trust'. Verifique permissões de administrador."
  exit $LASTEXITCODE
}

Write-Host "[OK] CA local do Caddy confiada (idempotente)."
