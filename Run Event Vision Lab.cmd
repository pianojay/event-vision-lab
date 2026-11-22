@echo off
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -File "%~dp0run-lab.ps1" %*
set "lab_exit=%errorlevel%"
if not "%lab_exit%"=="0" pause
exit /b %lab_exit%
