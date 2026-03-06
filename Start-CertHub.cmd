@echo off
setlocal

REM garante que o working directory seja o do próprio .cmd (importante quando fixa na barra de tarefas)
cd /d "%~dp0"

REM escolhe pwsh (PowerShell 7) se existir, senão usa Windows PowerShell
set "PS=pwsh.exe"
where pwsh >nul 2>nul || set "PS=powershell.exe"

REM caminho do PS1 relativo ao .cmd (ajuste se seu ps1 estiver em outro lugar)
set "PS1=%~dp0scripts\dev\start-certhub.ps1"

if not exist "%PS1%" (
  echo ERRO: Nao encontrei o arquivo:
  echo "%PS1%"
  echo.
  pause
  exit /b 1
)

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
if errorlevel 1 (
  echo.
  echo O script retornou erro (errorlevel=%errorlevel%).
  pause
)