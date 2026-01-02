param(
    [string]$ApiBaseUrl = "http://localhost:8010",
    [string]$ApiV1Prefix = "/api/v1",
    [string]$TaskName = "CertHub Cleanup 18h",
    [string]$AgentExePath = "C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe",
    [string]$AgentLogPath = "$env:LOCALAPPDATA\CertHubAgent\logs\agent.log",
    [string]$DatabaseUrl
)

$ErrorActionPreference = "Stop"
$global:HasFailure = $false

function Write-Pass($Message) { Write-Host "PASS: $Message" -ForegroundColor Green }
function Write-Fail($Message) { Write-Host "FAIL: $Message" -ForegroundColor Red; $global:HasFailure = $true }
function Write-Warn($Message) { Write-Host "WARN: $Message" -ForegroundColor Yellow }
function Write-Info($Message) { Write-Host "INFO: $Message" -ForegroundColor Cyan }

function Normalize-DatabaseUrl([string]$Url) {
    if ([string]::IsNullOrWhiteSpace($Url)) { return $Url }
    if ($Url.StartsWith("postgresql+psycopg2://")) {
        return $Url -replace "^postgresql\+psycopg2://", "postgresql://"
    }
    return $Url
}

try {
    $healthUrl = "$ApiBaseUrl/health"
    $health = Invoke-RestMethod -Method Get -Uri $healthUrl -TimeoutSec 10
    if ($health.status -eq "ok") {
        Write-Pass "Health OK ($healthUrl)"
    } else {
        Write-Fail "Health returned unexpected payload: $($health | ConvertTo-Json -Compress)"
    }
} catch {
    Write-Fail "Health check failed ($healthUrl): $($_.Exception.Message)"
}

try {
    $apiProbeUrl = "$ApiBaseUrl$ApiV1Prefix"
    Invoke-WebRequest -Method Get -Uri $apiProbeUrl -TimeoutSec 10 | Out-Null
    Write-Warn "API v1 root responded without auth ($apiProbeUrl). Behavior depends on router config."
} catch {
    $statusCode = $null
    if ($null -ne $_.Exception -and $null -ne $_.Exception.Response) {
        $response = $_.Exception.Response
        if ($null -ne $response.StatusCode) {
            $statusCode = $response.StatusCode.value__
        }
    }
    if ($null -ne $statusCode) {
        if ($statusCode -in 401, 403, 404) {
            Write-Pass "API v1 reachable ($apiProbeUrl) returned HTTP $statusCode (expected)"
        } else {
            Write-Warn "API v1 probe returned HTTP $statusCode ($apiProbeUrl)"
        }
    } else {
        Write-Warn "API v1 probe failed with network/connection error: $($_.Exception.Message)"
    }
}

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $DatabaseUrl = $env:DATABASE_URL
}

if (-not [string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $normalizedDbUrl = Normalize-DatabaseUrl $DatabaseUrl
    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if ($null -eq $psql) {
        Write-Warn "psql not found. Install PostgreSQL client or use docker exec to run SQL."
    } else {
        try {
            & $psql $normalizedDbUrl -c "select 1;" | Out-Null
            Write-Pass "psql connectivity OK"
        } catch {
            Write-Warn "psql check failed: $($_.Exception.Message)"
        }
    }
} else {
    Write-Warn "DATABASE_URL not provided; skipping psql check."
}

try {
    $taskOutput = schtasks /Query /TN "$TaskName" /V /FO LIST 2>$null
    if ($LASTEXITCODE -eq 0 -and $taskOutput) {
        Write-Pass "Scheduled task exists: $TaskName"
        $taskToRun = ($taskOutput | Select-String -Pattern "^(Task To Run|Tarefa a ser executada):\s*(.+)$").Matches
        if ($taskToRun.Count -gt 0) {
            Write-Info ("Task To Run: " + $taskToRun[0].Groups[2].Value.Trim())
        } else {
            Write-Warn "Could not parse 'Task To Run' from scheduled task output."
        }
    } else {
        Write-Fail "Scheduled task not found: $TaskName"
    }
} catch {
    Write-Warn "Failed to query scheduled task: $($_.Exception.Message)"
}

if (Test-Path -Path $AgentExePath) {
    Write-Pass "Agent EXE found ($AgentExePath)"
} else {
    Write-Fail "Agent EXE not found ($AgentExePath)"
}

if (Test-Path -Path $AgentLogPath) {
    Write-Pass "Agent log found ($AgentLogPath)"
    Write-Info "Last 30 lines of agent.log:"
    Get-Content $AgentLogPath -Tail 30
} else {
    Write-Warn "Agent log not found ($AgentLogPath). Run tray once to generate logs."
}

if ($global:HasFailure) {
    exit 1
}

exit 0
