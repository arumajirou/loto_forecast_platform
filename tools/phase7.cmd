@echo off
setlocal

if "%~1"=="" goto :usage

if /I "%~1"=="forensic" goto :forensic
if /I "%~1"=="live" goto :live
if /I "%~1"=="replay" goto :replay

echo ERROR: unknown Phase 7 command: %~1
goto :usage

:forensic
call "%~dp0phase7_holdout_runner\run_frozen_config_forensics.cmd"
exit /b %ERRORLEVEL%

:live
call "%~dp0phase7_holdout_runner\run_pr355_live_mapping_diagnostic.cmd"
exit /b %ERRORLEVEL%

:replay
call "%~dp0phase7_holdout_runner\run_pr355_replay_only.cmd"
exit /b %ERRORLEVEL%

:usage
echo Usage:
echo   tools\phase7.cmd forensic
echo   tools\phase7.cmd live
echo   tools\phase7.cmd replay
exit /b 2
