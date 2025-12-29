param(
    [string]$SourceExe = "C:\Temp\CerthubAgent\publish\Certhub.Agent.exe",
    [string]$InstallDir = "C:\ProgramData\CertHubAgent",
    [switch]$StartAgent,
    [string]$ApiBaseUrl = "<API_BASE_URL>",
    [string]$DeviceId = "<DEVICE_ID>",
    [string]$DeviceToken = "<DEVICE_TOKEN>"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $SourceExe)) {
    throw "Source exe not found: $SourceExe"
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$destinationExe = Join-Path $InstallDir "Certhub.Agent.exe"
Copy-Item -Path $SourceExe -Destination $destinationExe -Force
Unblock-File -Path $destinationExe

$runKeyPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runValueName = "CerthubAgent"
$runCommand = "`"$destinationExe`" --minimized"

New-Item -Path $runKeyPath -Force | Out-Null
Set-ItemProperty -Path $runKeyPath -Name $runValueName -Value $runCommand

if ($StartAgent.IsPresent) {
    Start-Process -FilePath $destinationExe -ArgumentList "--minimized"
}

Write-Host "" 
Write-Host "Agent deployed to: $destinationExe" -ForegroundColor Green
Write-Host "Auto-start configured (HKCU Run)." -ForegroundColor Green
if ($StartAgent.IsPresent) {
    Write-Host "Agent started." -ForegroundColor Green
}

Write-Host "" 
Write-Host "Pair device (tray -> Pair device):" -ForegroundColor Yellow
Write-Host "  API Base URL : $ApiBaseUrl"
Write-Host "  Device ID    : $DeviceId"
Write-Host "  Device Token : $DeviceToken"
