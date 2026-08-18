@echo off
setlocal

set "SCRIPT=%~dp0pr355_replay_only_bootstrap.py"
set "PY=%USERPROFILE%\Downloads\automlforecast-api-smoke-20260817-163008\venv\Scripts\python.exe"

if not exist "%SCRIPT%" (
  echo ERROR: replay bootstrap script not found: %SCRIPT%
  exit /b 2
)

if not exist "%PY%" (
  where python >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Python runtime not found.
    exit /b 3
  )
  set "PY=python"
)

"%PY%" "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"
exit /b %RC%
