@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0..\..\.."
set /p SUMMARY=Enter a 150-200 character summary: 
if not defined SUMMARY (
  echo Summary is required.
  popd
  pause
  exit /b 1
)
python sync_homepage.py --apply --summary "%SUMMARY%"
set EXIT_CODE=%ERRORLEVEL%
popd
pause
exit /b %EXIT_CODE%
