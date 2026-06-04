@echo off
REM Double-click this to launch Lexorama (API + web) and open the browser.
REM It just runs the PowerShell launcher next to it, bypassing execution policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-lexorama.ps1"
