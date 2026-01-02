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

Write-Host "Validating scheduled task..." -ForegroundColor Cyan
schtasks /Query /TN "$taskName" /V /FO LIST
