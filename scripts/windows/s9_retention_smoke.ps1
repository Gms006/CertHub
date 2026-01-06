param(
    [string]$ApiBaseUrl = "http://localhost:8010",
    [string]$ApiV1Prefix = "/api/v1",
    [string]$CertId,
    [string]$DeviceId,
    [string]$JwtView,
    [string]$JwtAdmin,
    [string]$AgentExePath = "C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe",
    [string]$DatabaseUrl,
    [string]$Thumbprint
)

$ErrorActionPreference = "Stop"

function Write-Info($Message) { Write-Host "INFO: $Message" -ForegroundColor Cyan }
function Write-Warn($Message) { Write-Host "WARN: $Message" -ForegroundColor Yellow }
function Write-Pass($Message) { Write-Host "PASS: $Message" -ForegroundColor Green }
function Write-Fail($Message) { Write-Host "FAIL: $Message" -ForegroundColor Red }

if ([string]::IsNullOrWhiteSpace($CertId) -or [string]::IsNullOrWhiteSpace($DeviceId)) {
    Write-Fail "CertId e DeviceId são obrigatórios."
    exit 1
}

if ([string]::IsNullOrWhiteSpace($JwtView) -or [string]::IsNullOrWhiteSpace($JwtAdmin)) {
    Write-Warn "JWTs não fornecidos. Os exemplos abaixo exigem JwtView/JwtAdmin."
}

$baseUrl = "$ApiBaseUrl$ApiV1Prefix"

if (-not [string]::IsNullOrWhiteSpace($JwtView)) {
    $keepUntil = (Get-Date).ToUniversalTime().AddMinutes(2).ToString("o")
    $viewResponse = Invoke-RestMethod -Method Post "$baseUrl/certificados/$CertId/install" `
        -Headers @{ Authorization = "Bearer $JwtView" } `
        -ContentType "application/json" `
        -Body (@{ device_id = $DeviceId; cleanup_mode = "KEEP_UNTIL"; keep_until = $keepUntil } | ConvertTo-Json)
    Write-Pass "VIEW criou job KEEP_UNTIL: $($viewResponse.id)"

    $keepUntilLocal = ([DateTimeOffset]::Parse($keepUntil)).ToLocalTime()
    $scheduledLocal = Get-Date -Date $keepUntilLocal -Second 0 -Millisecond 0
    if ($keepUntilLocal.Second -gt 0 -or $keepUntilLocal.Millisecond -gt 0) {
        $scheduledLocal = $scheduledLocal.AddMinutes(1)
    }
    $taskName = "CertHub KeepUntil $($scheduledLocal.ToString('yyyyMMdd-HHmm'))"
    Write-Info "Esperando task keep-until: $taskName"
    Write-Info "Validando que a task foi criada (schtasks /Query deve retornar 0)."
    $foundTask = $false
    for ($i = 0; $i -lt 12; $i++) {
        schtasks /Query /TN $taskName /FO LIST > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            $foundTask = $true
            break
        }
        Start-Sleep -Seconds 5
    }
    if ($foundTask) {
        Write-Pass "Task keep-until encontrada: $taskName"
        Write-Info "Disparando task keep-until manualmente."
        schtasks /Run /TN $taskName > $null 2>&1
        $deleted = $false
        for ($i = 0; $i -lt 12; $i++) {
            Start-Sleep -Seconds 5
            schtasks /Query /TN $taskName /FO LIST > $null 2>&1
            if ($LASTEXITCODE -ne 0) {
                $deleted = $true
                break
            }
        }
        if ($deleted) {
            Write-Pass "Task keep-until auto-deletou após execução."
        } else {
            Write-Warn "Task keep-until ainda existe após 60s; verifique auto-delete."
        }

        if (-not [string]::IsNullOrWhiteSpace($Thumbprint)) {
            $thumb = $Thumbprint.Replace(" ", "").ToUpperInvariant()
            $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Thumbprint -eq $thumb }
            if ($null -eq $cert) {
                Write-Pass "Certificado removido do Cert:\\CurrentUser\\My (thumbprint $thumb)."
            } else {
                Write-Warn "Certificado ainda presente no store (thumbprint $thumb)."
            }
        } else {
            Write-Warn "Thumbprint não fornecido; pulando validação do certificado removido."
        }
    } else {
        Write-Warn "Task keep-until não encontrada. Confirme se o Agent processou o job."
    }
}

if (-not [string]::IsNullOrWhiteSpace($JwtAdmin)) {
    $adminResponse = Invoke-RestMethod -Method Post "$baseUrl/certificados/$CertId/install" `
        -Headers @{ Authorization = "Bearer $JwtAdmin" } `
        -ContentType "application/json" `
        -Body (@{ device_id = $DeviceId; cleanup_mode = "EXEMPT"; keep_reason = "S9 smoke test" } | ConvertTo-Json)
    Write-Pass "ADMIN criou job EXEMPT: $($adminResponse.id)"
}

if (Test-Path -Path $AgentExePath) {
    Write-Info "Rodando cleanup manual: $AgentExePath --cleanup --mode manual"
    & $AgentExePath --cleanup --mode manual
} else {
    Write-Warn "Agent exe não encontrado em $AgentExePath"
}

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $DatabaseUrl = $env:DATABASE_URL
}

if (-not [string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if ($null -eq $psql) {
        Write-Warn "psql não encontrado. Instale o client ou use docker exec."
    } else {
        & $psql $DatabaseUrl -c "select action, meta_json, timestamp from audit_log where action in ('RETENTION_SET','CERT_REMOVED_18H','CERT_SKIPPED_RETENTION') order by timestamp desc limit 10;"
        & $psql $DatabaseUrl -c "select action, meta_json, timestamp from audit_log where action = 'CERT_REMOVED_18H' and meta_json->>'mode' = 'keep_until' order by timestamp desc limit 5;"
    }
} else {
    Write-Warn "DATABASE_URL não fornecido; pulando consulta de auditoria."
}
