@echo off
title Wallpaper Studio
cd /d "%~dp0"

rem Don't trust a name on PATH: "python" is often the Microsoft Store stub,
rem which just opens the Store. Only accept an interpreter that actually runs.
set "PYCMD="
for %%P in (py python python3) do (
    if not defined PYCMD (
        %%P -c "import sys; assert sys.version_info[0] == 3" >nul 2>nul && set "PYCMD=%%P"
    )
)

if defined PYCMD (
    %PYCMD% wallpaper_server.py
    goto :eof
)

echo Wallpaper Studio needs Python 3, and it isn't installed here.
echo.
echo If you have winget, this is the fastest fix:
echo     winget install -e --id Python.Python.3.12
echo.
choice /c YN /n /m "Open the Python download page instead? [Y/N] "
if errorlevel 2 goto :skip
start "" "https://www.python.org/downloads/"
echo.
echo Tick "Add python.exe to PATH" in the installer, then run start.bat again.
:skip
echo.
pause
