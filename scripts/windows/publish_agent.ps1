param(
    [string]$PublishDir = "C:\Temp\CerthubAgent\publish",
    [string]$ProjectPath = (Join-Path $PSScriptRoot "..\..\agent\windows\Certhub.Agent\Certhub.Agent"),
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [string]$ApiBaseUrl = "<API_BASE_URL>",
    [string]$DeviceId = "<DEVICE_ID>",
    [string]$DeviceToken = "<DEVICE_TOKEN>"
)

$ErrorActionPreference = "Stop"

$resolvedProjectPath = (Resolve-Path -Path $ProjectPath).Path
$resolvedPublishDir = $PublishDir

New-Item -ItemType Directory -Force -Path $resolvedPublishDir | Out-Null

Write-Host "Publishing Certhub.Agent from $resolvedProjectPath" -ForegroundColor Cyan
Write-Host "Output: $resolvedPublishDir" -ForegroundColor Cyan

Push-Location $resolvedProjectPath
try {
    dotnet restore
    dotnet publish -c $Configuration -r $Runtime --self-contained true `
        /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true `
        -o $resolvedPublishDir
}
finally {
    Pop-Location
}

Write-Host "" 
Write-Host "Pair device (tray -> Pair device):" -ForegroundColor Yellow
Write-Host "  API Base URL : $ApiBaseUrl"
Write-Host "  Device ID    : $DeviceId"
Write-Host "  Device Token : $DeviceToken"
