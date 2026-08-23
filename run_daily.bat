@echo off
REM 일일 목록 갱신 (Windows 작업 스케줄러에 등록해 매일 실행)
REM 작업 스케줄러 > 작업 만들기 > 트리거: 매일 06:00 > 동작: 이 파일 시작
cd /d "%~dp0"
python -m web.daily 30
