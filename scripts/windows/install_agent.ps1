param(
    [string]$PublishDir,
    [string]$ProjectPath = (Join-Path $PSScriptRoot "Certhub.Agent"),
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64"
)

$ErrorActionPreference = "Stop"

$installRoot = "C:\ProgramData\CertHubAgent"
$installPublishDir = Join-Path $installRoot "publish"
$exeName = "Certhub.Agent.exe"
$taskName = "CertHub Cleanup 18h"
$taskExePath = Join-Path $installPublishDir $exeName
$taskCommand = "`"$taskExePath`" --cleanup --mode scheduled"

if ([string]::IsNullOrWhiteSpace($PublishDir))
{
    $tempPublishDir = Join-Path $env:TEMP "CerthubAgent\publish"
    Write-Host "Publishing Certhub.Agent from $ProjectPath" -ForegroundColor Cyan
    Write-Host "Output: $tempPublishDir" -ForegroundColor Cyan

    New-Item -ItemType Directory -Force -Path $tempPublishDir | Out-Null

    Push-Location $ProjectPath
    try {
        dotnet restore
        dotnet publish -c $Configuration -r $Runtime --self-contained true `
            /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true `
            -o $tempPublishDir
    }
    finally {
        Pop-Location
    }

    $PublishDir = $tempPublishDir
}

$resolvedPublishDir = (Resolve-Path -Path $PublishDir).Path
$sourceExe = Join-Path $resolvedPublishDir $exeName

if (-not (Test-Path $sourceExe))
{
    throw "Publish output not found: $sourceExe"
}

Write-Host "Installing agent to $installPublishDir" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $installPublishDir | Out-Null
Copy-Item -Path (Join-Path $resolvedPublishDir "*") -Destination $installPublishDir -Recurse -Force

Write-Host "Creating scheduled task '$taskName'" -ForegroundColor Cyan
schtasks /Delete /TN "$taskName" /F | Out-Null
schtasks /Create /TN "$taskName" /SC DAILY /ST 18:00 /TR "$taskCommand" /RL LIMITED /IT /F | Out-Null

Write-Host "Creating Task Scheduler folder structure..." -ForegroundColor Cyan
try {
    $service = New-Object -ComObject("Schedule.Service")
    $service.Connect()
    $rootFolder = $service.GetFolder("\")
    
    # Cria \CertHub
    try {
        $certHubFolder = $service.GetFolder("\CertHub")
        Write-Host "  Folder \CertHub already exists"
    } catch {
        $certHubFolder = $rootFolder.CreateFolder("CertHub")
        Write-Host "  Created folder \CertHub"
    }
    
    # Cria \CertHub\{username}
    $userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name.Split('\')[-1]
    $userFolderPath = "\CertHub\$userName"
    try {
        $userFolder = $service.GetFolder($userFolderPath)
        Write-Host "  Folder $userFolderPath already exists"
    } catch {
        $userFolder = $certHubFolder.CreateFolder($userName)
        Write-Host "  Created folder $userFolderPath"
    }
    
    Write-Host "Task Scheduler folder structure ready" -ForegroundColor Green
} catch {
    Write-Warning "Failed to create Task Scheduler folder structure: $_"
    Write-Warning "Keep-until tasks may require admin privileges on first run"
}

Write-Host "Setting permissions on Task Scheduler folders..." -ForegroundColor Cyan
try {
    $currentUserName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name.Split('\')[-1]
    $taskFolderPath = "C:\Windows\System32\tasks\CertHub\$currentUserName"
    $domainUserName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    
    if (Test-Path $taskFolderPath) {
        icacls $taskFolderPath /grant "${domainUserName}:(F)" /T /Q
        Write-Host "  Permissions granted for $domainUserName on $taskFolderPath" -ForegroundColor Green
    }
} catch {
    Write-Warning "Failed to set permissions: $_"
    Write-Warning "You may need to run the icacls command manually as administrator"
}

Write-Host "Validating scheduled task..." -ForegroundColor Cyan
schtasks /Query /TN "$taskName" /V /FO LIST
