@echo off
setlocal EnableExtensions

set "SCRIPT=%~dp0phase7_holdout_runner\evidence_bundle.py"
set "MODE=%~1"

if /I "%MODE%"=="export" goto :export
if /I "%MODE%"=="status" goto :status
goto :usage

:status
echo PHASE7_EVIDENCE_TOOL=v1
echo DEFAULT_DOWNLOADS=%USERPROFILE%\Downloads
exit /b 0

:export
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo STATUS=BLOCKED
    echo REASON=Python 3 is required for evidence export
    exit /b 20
)

echo [1/3]  33%% verify exact Phase 7 evidence
echo [2/3]  66%% create portable evidence ZIP
%PY% "%SCRIPT%" export
if errorlevel 1 exit /b %ERRORLEVEL%
echo [3/3] 100%% portable evidence bundle complete
echo NEXT=Copy the emitted ZIP to Linux and run: bash tools/phase7-evidence.sh import ^<bundle.zip^>
exit /b 0

:usage
echo Usage:
echo   tools\phase7-evidence.cmd status
echo   tools\phase7-evidence.cmd export
exit /b 2
