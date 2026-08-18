@echo off
setlocal

if "%~1"=="" goto :usage

if /I "%~1"=="forensic" (
  shift
  call "%~dp0phase7_holdout_runner\run_frozen_config_forensics.cmd" %*
  exit /b %ERRORLEVEL%
)

if /I "%~1"=="live" (
  shift
  call "%~dp0phase7_holdout_runner\run_pr355_live_mapping_diagnostic.cmd" %*
  exit /b %ERRORLEVEL%
)

echo ERROR: unknown Phase 7 command: %~1
:usage
echo Usage:
echo   tools\phase7.cmd forensic
echo   tools\phase7.cmd live
exit /b 2
