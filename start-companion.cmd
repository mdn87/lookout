@echo off
rem Start Lookout with BWS when local references are configured.
cd /d "%~dp0"
if exist "config\glas.local.json" (
  start "" ".venv\Scripts\pythonw.exe" scripts\with-glas.py
) else (
  start "" ".venv\Scripts\pythonw.exe" -m companion.app
)
