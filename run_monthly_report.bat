@echo off
REM 월간 보고서 — 매월 1일 13:30 작업 스케줄러에서 실행(인자 없으면 지난달 대상).
REM 접속 로그는 14일만 보존되므로 성장 지표는 docs/daily-reports/ 의 방문자 표를 누적한다.
chcp 65001 > nul
cd /d "%~dp0"
python tools\monthly_report.py
exit /b %errorlevel%
