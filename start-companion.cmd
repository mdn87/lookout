@echo off
rem Start Lookout with BWS when local references are configured.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" scripts\with-glas.py
