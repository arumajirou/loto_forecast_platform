@echo off
setlocal

set "PYTHON=%USERPROFILE%\Downloads\automlforecast-api-smoke-20260817-163008\venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" "%~dp0sealed_holdout_execution.py"
exit /b %ERRORLEVEL%
