@echo off
rem Build the Windows zip. Run this ON a Windows machine with Python 3 installed.
rem The people who download the zip do NOT need Python -- it ends up inside the exe.
cd /d "%~dp0"

python -m pip install --upgrade pyinstaller || goto :fail
pyinstaller wallpaper-studio.spec --noconfirm || goto :fail

if exist stage rmdir /s /q stage
mkdir "stage\Wallpaper Studio"
copy "dist\WallpaperStudio.exe" "stage\Wallpaper Studio\" >nul
copy "packaging\README-Windows.txt" "stage\Wallpaper Studio\README.txt" >nul

if exist WallpaperStudio-Windows-x64.zip del WallpaperStudio-Windows-x64.zip
powershell -NoProfile -Command "Compress-Archive -Path 'stage/Wallpaper Studio' -DestinationPath 'WallpaperStudio-Windows-x64.zip'" || goto :fail

echo.
echo Done: WallpaperStudio-Windows-x64.zip
pause
goto :eof

:fail
echo.
echo Build failed. Is Python 3 installed and on PATH?
pause
