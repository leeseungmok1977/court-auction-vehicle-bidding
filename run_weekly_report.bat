@echo off
REM 주간 보고서 — 토요일 13:00 작업 스케줄러에서 실행.
REM 전문가 패널 클라우드 루틴(토 09:20)이 docs/reviews/ 에 커밋한 뒤여야 그 주 패널이 잡힌다.
REM 운영 서버와 이 PC를 읽기만 하며 외부 사이트에는 요청하지 않는다.
chcp 65001 > nul
cd /d "%~dp0"
python tools\weekly_report.py
exit /b %errorlevel%
