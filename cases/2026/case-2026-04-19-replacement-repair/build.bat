@echo off
setlocal
pushd "%~dp0..\..\.."
set /p SUMMARY=150~200자 요약문을 입력하세요: 
if not defined SUMMARY (
  echo 요약문이 필요합니다.
  popd
  pause
  exit /b 1
)
python sync_homepage.py --apply --summary "%SUMMARY%"
set EXIT_CODE=%ERRORLEVEL%
popd
pause
exit /b %EXIT_CODE%
