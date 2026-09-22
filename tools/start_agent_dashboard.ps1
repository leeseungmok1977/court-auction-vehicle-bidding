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
python tools/agent_dashboard.py --port 8765
exit $LASTEXITCODE
