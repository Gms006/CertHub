param(
    [ValidateSet("Dev", "PublicTls")]
    [string]$Mode = "Dev",
    [string]$CertDomain,
    [string]$LeEmail
)

# scripts/dev/start-certhub.ps1
# Inicia infra (docker), backend (uvicorn), worker (rq), watcher (pfx) e caddy
# Abrindo cada um em uma janela do PowerShell separada.

$ErrorActionPreference = "Stop"

$SharedVenvActivate = "G:\PMA\SCRIPTS\.venv\Scripts\Activate.ps1"
$SharedPythonExe    = "G:\PMA\SCRIPTS\.venv\Scripts\python.exe"
$DefaultCertDomain  = "certhub.duckdns.org"
$DefaultLeEmail     = "mariaclarasc.netocontabilidade@gmail.com"

if ([string]::IsNullOrWhiteSpace($CertDomain)) {
    $CertDomain = $DefaultCertDomain
}
if ([string]::IsNullOrWhiteSpace($LeEmail)) {
    $LeEmail = $DefaultLeEmail
}

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

function Resolve-LeEmail {
    param(
        [string]$ExplicitValue
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitValue)) {
        return $ExplicitValue.Trim()
    }

    if (-not [string]::IsNullOrWhiteSpace($env:LE_EMAIL)) {
        return $env:LE_EMAIL.Trim()
    }

    $inputValue = Read-Host "Informe LE_EMAIL para emissão ACME/Let's Encrypt"
    if ([string]::IsNullOrWhiteSpace($inputValue)) {
        throw "LE_EMAIL é obrigatório no modo PublicTls (parâmetro -LeEmail, env LE_EMAIL ou prompt)."
    }

    return $inputValue.Trim()
}

function Ensure-ProdCaddyfile {
    param(
        [string]$TemplatePath,
        [string]$ProdPath,
        [string]$Domain,
        [string]$Email
    )

    if (Test-Path -Path $ProdPath) {
        return
    }

    if (-not (Test-Path -Path $TemplatePath)) {
        throw "Template não encontrado: $TemplatePath"
    }

    $templateContent = Get-Content -Path $TemplatePath -Raw -Encoding UTF8
    $prodContent = $templateContent.Replace('{$CERT_DOMAIN}', $Domain).Replace('{$LE_EMAIL}', $Email)
    Set-Content -Path $ProdPath -Value $prodContent -Encoding UTF8
    Write-Host "[OK] Caddyfile de produção gerado: $ProdPath"
}

# Resolve repo root a partir do local do script (scripts/dev -> repo root)
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

Write-Host "RepoRoot: $RepoRoot"
Write-Host "Mode: $Mode"

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

if ($Mode -eq "PublicTls") {
    $frontendDist = Join-Path $RepoRoot "frontend\dist"
    if (-not (Test-Path -Path $frontendDist)) {
        throw "frontend/dist não encontrado. Gere o frontend antes (ex.: cd frontend; npm run build)."
    }

    if (-not (Get-Command caddy -ErrorAction SilentlyContinue)) {
        throw "Comando 'caddy' não encontrado no PATH."
    }

    $resolvedLeEmail = Resolve-LeEmail -ExplicitValue $LeEmail
    $infraHttpsDir = Join-Path $RepoRoot "infra\https"
    $prodTemplatePath = Join-Path $infraHttpsDir "Caddyfile.prod.template"
    $prodCaddyfilePath = Join-Path $infraHttpsDir "Caddyfile.prod"

    Ensure-ProdCaddyfile -TemplatePath $prodTemplatePath -ProdPath $prodCaddyfilePath -Domain $CertDomain -Email $resolvedLeEmail

    $CaddyPublicCmd = @"
`$host.ui.rawui.WindowTitle = 'CertHub - Caddy (PublicTls)'
cd '$infraHttpsDir'
Write-Host 'Validando Caddyfile.prod...'
caddy validate --config .\Caddyfile.prod --adapter caddyfile
if (`$LASTEXITCODE -ne 0) { throw 'Falha na validação do Caddyfile.prod' }
Write-Host 'Iniciando Caddy com Caddyfile.prod...'
caddy run --config .\Caddyfile.prod --adapter caddyfile
"@

    Start-Process powershell -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$CaddyPublicCmd)
    Write-Host "Tudo iniciado (PublicTls). Acesse: https://$CertDomain/"
} else {
    $CaddyCmd = @"
`$host.ui.rawui.WindowTitle = 'CertHub - Caddy'
cd '$RepoRoot'
.\scripts\windows\s10_run_caddy.ps1
"@
    Start-Process powershell -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$CaddyCmd)
    Write-Host "Tudo iniciado (Dev). Acesse: https://certhub.local/"
}
