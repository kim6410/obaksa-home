@echo off
setlocal
chcp 65001 >nul
title 오박사 시공사례 재빌드

set "CASE_DIR=%~dp0"
set "PROJECT_ROOT=G:\OneDrive\01_울산오박사인테리어\obaksa_site\obaksa-home"

echo.
echo Current case folder:
echo %CASE_DIR%
echo.
echo Rebuilding index.md and image_manifest.json into HTML...
echo.

pushd "%PROJECT_ROOT%"
python sync_homepage.py --rebuild-case "%CASE_DIR%"
set EXIT_CODE=%ERRORLEVEL%
popd
echo.
echo Rebuild complete.
echo Commit / push separately if you want to publish the change.
echo.
pause
exit /b %EXIT_CODE%
