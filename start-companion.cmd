@echo off
rem Start the Lookout companion in the tray, without a console window.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m companion.app
