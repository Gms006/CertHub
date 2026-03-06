# scripts/dev/start-certhub.ps1
# Inicia infra (docker), backend (uvicorn), worker (rq), watcher (pfx) e caddy
# Abrindo cada um em uma janela do PowerShell separada.

$ErrorActionPreference = "Stop"

$SharedVenvActivate = "G:\PMA\SCRIPTS\.venv\Scripts\Activate.ps1"
$SharedPythonExe    = "G:\PMA\SCRIPTS\.venv\Scripts\python.exe"

function Wait-TcpPort {
    param(
        [string]$TargetHost = "127.0.0.1",
        [int]$Port,
        [int]$TimeoutSeconds = 60
    )
    $start = Get-Date
    while (((Get-Date) - $start).TotalSeconds -lt $TimeoutSeconds) {
        try {
            if (Test-NetConnection -ComputerName $TargetHost -Port $Port -InformationLevel Quiet) {
                return $true
            }
        } catch {}
        Start-Sleep -Seconds 1
    }
    return $false
}

# Resolve repo root a partir do local do script (scripts/dev -> repo root)
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

Write-Host "RepoRoot: $RepoRoot"

# 1) Infra (docker)
Write-Host "Subindo infra (docker compose)..."
Push-Location $RepoRoot
docker compose -f "infra/docker-compose.yml" up -d
Pop-Location

# Helper: ativa .venv se existir (mesmo padrão em todas janelas)
$ActivateVenv = @"
if (-not (Test-Path '$SharedVenvActivate')) { throw 'Não achei Activate.ps1 em: $SharedVenvActivate' }
if (-not (Test-Path '$SharedPythonExe'))    { throw 'Não achei python.exe em: $SharedPythonExe' }
. '$SharedVenvActivate'
"@

# 2) Backend (uvicorn)
$BackendCmd = @"
`$host.ui.rawui.WindowTitle = 'CertHub - Backend (uvicorn)'
$ActivateVenv
cd '$RepoRoot\backend'
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010 --env-file .\.env
"@
Start-Process powershell -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$BackendCmd)

# 3) Worker (rq)
$WorkerCmd = @"
`$host.ui.rawui.WindowTitle = 'CertHub - Worker (rq)'
$ActivateVenv
cd '$RepoRoot\backend'
`$env:REDIS_URL='redis://localhost:6379/0'
`$env:RQ_QUEUE_NAME='certs'
`$env:CERTIFICADOS_ROOT='G:\CERTIFICADOS DIGITAIS'
python -m app.workers.rq_worker
"@
Start-Process powershell -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$WorkerCmd)

# 4) Watcher (pfx)
$WatcherCmd = @"
`$host.ui.rawui.WindowTitle = 'CertHub - Watcher (pfx_directory)'
$ActivateVenv
cd '$RepoRoot\backend'
`$env:REDIS_URL='redis://localhost:6379/0'
`$env:RQ_QUEUE_NAME='certs'
`$env:ORG_ID='1'
`$env:CERTIFICADOS_ROOT='G:\CERTIFICADOS DIGITAIS'
`$env:WATCHER_DEBOUNCE_SECONDS='2'
`$env:WATCHER_MAX_EVENTS_PER_MINUTE='60'
python -m app.watchers.pfx_directory
"@
Start-Process powershell -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$WatcherCmd)

# 5) Caddy (só depois do backend responder na 8010)
Write-Host "Aguardando backend na porta 8010 para iniciar o Caddy..."
if (-not (Wait-TcpPort -Port 8010 -TimeoutSeconds 90)) {
    throw "Backend não subiu na 8010 a tempo. Não vou iniciar o Caddy."
}

$CaddyCmd = @"
`$host.ui.rawui.WindowTitle = 'CertHub - Caddy'
cd '$RepoRoot'
.\scripts\windows\s10_run_caddy.ps1
"@
Start-Process powershell -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$CaddyCmd)

Write-Host "Tudo iniciado. Acesse: https://certhub.local/"