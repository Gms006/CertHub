param(
    [string]$ApiBaseUrl = "http://localhost:8010",
    [string]$ApiV1Prefix = "/api/v1",
    [string]$CertId,
    [string]$DeviceId,
    [string]$JwtView,
    [string]$JwtAdmin,
    [string]$AgentExePath = "C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe",
    [string]$DatabaseUrl
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
    $keepUntil = (Get-Date).ToUniversalTime().AddHours(2).ToString("o")
    $viewResponse = Invoke-RestMethod -Method Post "$baseUrl/certificados/$CertId/install" `
        -Headers @{ Authorization = "Bearer $JwtView" } `
        -ContentType "application/json" `
        -Body (@{ device_id = $DeviceId; cleanup_mode = "KEEP_UNTIL"; keep_until = $keepUntil } | ConvertTo-Json)
    Write-Pass "VIEW criou job KEEP_UNTIL: $($viewResponse.id)"
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
    }
} else {
    Write-Warn "DATABASE_URL não fornecido; pulando consulta de auditoria."
}
