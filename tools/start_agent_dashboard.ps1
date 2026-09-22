# 에이전트 현황 대시보드를 띄운다. 로그온 예약 작업이 이 파일 하나만 가리키게 하기 위한 런처.
#
# 왜 별도 파일인가: schtasks /tr 에 `powershell -Command "cd '...'; python ..."` 같은 긴 명령을
# 인용부호째로 밀어 넣으면 인용이 중첩돼 조용히 어긋난다. 2026-09-23 이 세션에서만 인용 문제로
# 커밋이 두 번, 측정 스크립트가 두 번 깨졌다. 예약 작업에는 **파일 경로 하나만** 넘긴다.
#
# 창을 숨기는 것은 예약 작업 쪽(powershell -WindowStyle Hidden)이 맡는다. 여기서 pythonw 를
# 쓰지 않는 이유가 있다 — pythonw 는 sys.stdout/stderr 가 None 이라, 시작 실패를 알리는
# print(file=sys.stderr) 가 도리어 예외를 낸다. 콘솔은 두되 보이지 않게 하는 편이 안전하다.

$ErrorActionPreference = 'Continue'
Set-Location (Split-Path $PSScriptRoot -Parent)      # tools/ 의 부모 = 저장소 루트
$env:PYTHONIOENCODING = 'utf-8'

# 이미 떠 있으면 파이썬 쪽 포트 가드가 안내를 찍고 종료코드 1 로 빠진다(두 번 띄우지 않는다).
#
# --host 0.0.0.0 : 사내망의 다른 PC 에서도 보기 위해 연다(오너 요청 2026-09-23).
#   ★ 이 화면에는 로그인이 없다. 그래서 밖에 열 때는 파이썬 쪽이 **열쇠를 강제**한다 —
#     `data/dashboard_token.txt`(git 제외) 의 토큰이 없는 요청은 403 이다. 실측 확인:
#     키 없음 403 · 틀린 키 403 · 맞는 키 200 (/ 와 /api/state 양쪽).
#   ★ 여기서 --host 를 빼면 로컬 전용으로 되돌아간다. 되돌릴 때는 그 한 군데만 지우면 된다.
#     반대로 이 줄을 안 고쳐 두면 **재부팅 때마다 사내망 접속이 조용히 끊긴다** — 화면은
#     멀쩡히 뜨는데 다른 PC 에서만 안 보여서, 원인을 찾는 데 시간이 걸린다.
python tools/agent_dashboard.py --port 8765 --host 0.0.0.0
exit $LASTEXITCODE
