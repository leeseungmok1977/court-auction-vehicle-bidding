@echo off
REM ============================================================================
REM  집 회선 경유 터널(F안) — 엔카 전용 프록시(8888) + EC2 역방향 SSH 터널
REM   EC2 127.0.0.1:18080  --(SSH -R)-->  이 PC 127.0.0.1:8888  --> encar.com
REM  사용: 더블클릭. 이 창이 열려 있는 동안만 터널이 유지됩니다(끊기면 15초 후 자동 재접속).
REM  자동 시작(로그온 시): docs/HOME_TUNNEL.md 참고.
REM ============================================================================
setlocal
set "KEY=%USERPROFILE%\Downloads\naechaget.pem"
set "HOST=ubuntu@43.202.126.180"
cd /d "%~dp0"

start "naechaget-home-proxy" /min python home_proxy.py

:loop
echo [%date% %time%] tunnel connecting...
ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -i "%KEY%" -R 127.0.0.1:18080:127.0.0.1:8888 %HOST%
echo [%date% %time%] tunnel closed (exit %errorlevel%) - retry in 15s
timeout /t 15 /nobreak >nul
goto loop
