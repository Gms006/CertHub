param(
  [string]$Domain = "certhub.local",
  [string]$IP = "127.0.0.1"
)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Error "Este script precisa ser executado como Administrador."
  exit 1
}

$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$backupPath = "$hostsPath.bak"
$entry = "$IP`t$Domain"

$hostsContent = Get-Content -Path $hostsPath -ErrorAction Stop
$activeDomainLines = $hostsContent | Where-Object { $_ -match "^\s*[^#].*\b$([regex]::Escape($Domain))\b" }
$exactEntryExists = $hostsContent | Where-Object { $_ -match "^\s*$([regex]::Escape($IP))\s+$([regex]::Escape($Domain))(\s+.*)?$" }

if ($exactEntryExists) {
  Write-Host "[OK] Entrada já existe em hosts: $entry"
  exit 0
}

if ($activeDomainLines) {
  Write-Warning "[WARN] Já existe entrada ativa para $Domain com outro IP. Nenhuma alteração aplicada."
  $activeDomainLines | ForEach-Object { Write-Host "  $_" }
  exit 1
}

if (-not (Test-Path -Path $backupPath)) {
  Copy-Item -Path $hostsPath -Destination $backupPath -Force
  Write-Host "[OK] Backup criado: $backupPath"
}

Add-Content -Path $hostsPath -Value $entry
Write-Host "[OK] Entrada adicionada em hosts: $entry"
