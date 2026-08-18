@echo off
setlocal

set "PYTHON=C:\Users\bp00425\Downloads\automlforecast-api-smoke-20260817-163008\venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" "%~dp0main_preflight.py"
exit /b %ERRORLEVEL%
