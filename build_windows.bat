@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher "py" was not found. Install Python 3.12 from python.org and retry.
  pause
  exit /b 1
)

set "ISCC="
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo Inno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php and retry.
  pause
  exit /b 1
)

if not exist .venv-build\Scripts\python.exe py -3.12 -m venv .venv-build
if errorlevel 1 goto :failed

.venv-build\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :failed
.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 goto :failed
.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean ReadNovelFull.spec
if errorlevel 1 goto :failed

if exist release rmdir /s /q release
mkdir release
if errorlevel 1 goto :failed
set "APP_VERSION=1.0.0"
"%ISCC%" installer.iss
if errorlevel 1 goto :failed

echo.
echo Installer created: release\ReadNovelFull-Setup-Windows-x64.exe
echo Upload this installer as the GitHub Release asset.
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error above.
pause
exit /b 1
