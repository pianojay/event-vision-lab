@echo off
pwsh -NoProfile -File "%~dp0run-lab.ps1" %*
if errorlevel 1 pause
