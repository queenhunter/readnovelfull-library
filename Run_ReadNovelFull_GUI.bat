@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0ReadNovelFull.exe" (
  start "" "%~dp0ReadNovelFull.exe"
  exit /b 0
)
if exist "%~dp0release\ReadNovelFull-Windows-x64\ReadNovelFull.exe" (
  start "" "%~dp0release\ReadNovelFull-Windows-x64\ReadNovelFull.exe"
  exit /b 0
)

python -c "import PySide6, bs4, requests" >nul 2>nul
if errorlevel 1 (
  echo The packaged app is not here yet, and source-run dependencies are missing.
  echo For the downloadable app, push a v1.0.0 tag to GitHub to build a release.
  echo For local source development, install requirements-build.txt manually.
  pause
  exit /b 1
)
python "%~dp0ReadNovelFull_GUI.py"
if errorlevel 1 pause
