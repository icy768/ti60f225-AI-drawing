@echo off
setlocal
cd /d "%~dp0"
if not defined STYLECAM_PYTHON set "STYLECAM_PYTHON=python"
"%STYLECAM_PYTHON%" build_fw.py
exit /b %errorlevel%
