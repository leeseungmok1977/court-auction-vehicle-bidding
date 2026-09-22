@echo off
rem 로그온 예약 작업(naechaget-agent-dashboard)이 부르는 진입점.
rem 예약 작업에는 **이 파일 경로 하나만** 넘긴다 — /tr 안에 긴 명령을 인용부호째 넣으면
rem 인용이 중첩돼 조용히 어긋난다(2026-09-23 이 세션에서만 인용 문제로 네 번 깨졌다).
rem %~dp0 은 이 파일이 있는 폴더(tools\)라, 저장소를 옮겨도 따라간다.
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0start_agent_dashboard.ps1"
