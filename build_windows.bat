@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher "py" was not found. Install Python 3.12 from python.org and retry.
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
set "STAGE=release\ReadNovelFull-Windows-x64"
mkdir "%STAGE%"
if errorlevel 1 goto :failed
xcopy /e /i /y "dist\ReadNovelFull\*" "%STAGE%\"
if errorlevel 1 goto :failed
copy /y README_RELEASE.txt "%STAGE%\README.txt" >nul
if errorlevel 1 goto :failed
copy /y THIRD_PARTY_NOTICES.txt "%STAGE%\THIRD_PARTY_NOTICES.txt" >nul
if errorlevel 1 goto :failed
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath 'release\ReadNovelFull-Windows-x64.zip' -Force"
if errorlevel 1 goto :failed

echo.
echo Release package created: release\ReadNovelFull-Windows-x64.zip
echo You can run ReadNovelFull.exe from the extracted folder.
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error above.
pause
exit /b 1
