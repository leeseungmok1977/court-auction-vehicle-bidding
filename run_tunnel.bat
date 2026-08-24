@echo off
REM ── 무료 외부접속 터널 (Cloudflare Quick Tunnel) ──────────────────
REM  사용법:
REM   1) 먼저 다른 창에서 서버 실행:  python run_web.py
REM   2) 이 파일 실행 → 아래 콘솔에 https://xxxx.trycloudflare.com 주소가 뜸
REM  주의: 이 PC가 켜져 있고 서버가 돌고 있어야 접속됨. 창을 닫으면 터널이 내려감.
REM       주소는 실행할 때마다 새로 바뀜(무료 quick tunnel 특성).
where cloudflared >nul 2>nul && (
  cloudflared tunnel --url http://localhost:8000 --no-autoupdate
) || (
  "%USERPROFILE%\tools\cloudflared.exe" tunnel --url http://localhost:8000 --no-autoupdate
)
