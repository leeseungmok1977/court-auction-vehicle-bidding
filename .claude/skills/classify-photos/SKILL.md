---
name: classify-photos
description: 경매차량 사진 비전 분류 루틴. 미분류(photo_order 없는) 건수를 먼저 확인하고, 있으면 전면·측면·후면 순서로 자동 분류(멀티 에이전트)한 뒤 VM 반영 패치까지 만든다. 사용자가 "사진 분류", "썸네일 정렬", "미분류 확인", /classify-photos 라고 할 때.
---

# 경매차량 사진 자동 분류 루틴

목적: 최근 수집된 물건은 `photo_order`(비전 분류 순서)가 없어 목록 썸네일이 원본순(지도·서류 먼저)으로 나온다. 이 루틴으로 **미분류만 증분 분류**해 전면·측면·후면부터 나오게 하고, VM에 반영한다.

전제: 이 작업은 **Workflow 도구(멀티 에이전트 비전 판독)** 를 쓴다. 프로젝트 루트(`c:\Users\14ZB95N\법원경매조회 및 분석`)에서 실행. 파이썬은 `PYTHONIOENCODING=utf-8 python`.

## 1) 미분류 건수 확인 (항상 먼저)
```
PYTHONIOENCODING=utf-8 python scripts/photo_classify.py status
```
출력의 `UNCLASSIFIED=N` 을 읽는다. **N을 사용자에게 보고**한다.
- N == 0 → "미분류 0건, 분류할 것 없음" 보고 후 **종료**.
- N > 0 → 아래 진행. (N이 아주 크면(예: >800) `prep --limit 600` 등으로 나눠 부하 통제)

## 2) 몽타주 생성 (prep)
```
PYTHONIOENCODING=utf-8 python scripts/photo_classify.py prep
```
`data/_photo_work/` 에 `0001.png…` 몽타주와 `args.json`({base,total}), `manifest.json` 생성. 출력의 `args` 를 확인.

## 3) 비전 분류 워크플로 실행
`data/_photo_work/args.json` 의 base·total 을 인자로 저장된 워크플로 실행(백그라운드):
```
Workflow({scriptPath: "scripts/photo_classify_workflow.js", args: {"base": <args.base>, "total": <args.total>}})
```
- 배치당 32건(≈15배치)으로 자동 분할. 완료 알림을 기다린다(폴링 금지).
- 완료 알림의 `<output-file>` 경로가 결과 JSON(래퍼 `{result:{results:[…]}}`).

## 4) 결과 반영 (ingest → apply)
```
PYTHONIOENCODING=utf-8 python scripts/photo_classify.py ingest "<완료 알림의 output-file 경로>"
PYTHONIOENCODING=utf-8 python scripts/photo_classify.py apply
```
`apply` 는 `photo_order` 를 로컬 DB에 반영하고 저확신(건설장비·선박 등) 건수를 요약한다.

## 5) 검증 (선택, 권장)
임시서버 띄워 최근 물건 썸네일이 전면부부터 나오는지 스크린샷 확인:
```
PYTHONIOENCODING=utf-8 python -m uvicorn web.app:app --port 8013 --log-level error &
```
Playwright로 `/vehicles?q=<차명>` 데스크톱 테이블(standalone 위장) 캡처. 끝나면 `pkill -f "port 8013"`.

## 6) VM 반영 패치 생성 + 안내
```
PYTHONIOENCODING=utf-8 python scripts/photo_classify.py export-patch
```
`data/photo_order_patch.json`(=`{물건id: [파일명…]}`) 생성. 사용자에게 아래 PowerShell 3줄 안내(SSH 키·IP는 project-deployment 메모리 참조: 키 `C:\Users\14ZB95N\Downloads\naechaget.pem`, `ubuntu@43.202.126.180`, 앱 `/home/ubuntu/app`, venv `.venv`):
```powershell
# (스크립트가 바뀐 경우에만) 코드 갱신
ssh -i C:\Users\14ZB95N\Downloads\naechaget.pem ubuntu@43.202.126.180 "cd app && git pull"
# 패치 업로드
scp -i C:\Users\14ZB95N\Downloads\naechaget.pem "C:\Users\14ZB95N\법원경매조회 및 분석\data\photo_order_patch.json" ubuntu@43.202.126.180:/home/ubuntu/app/data/
# VM DB 주입(기존 순서 보존, 재시작 불필요)
ssh -i C:\Users\14ZB95N\Downloads\naechaget.pem ubuntu@43.202.126.180 "cd app && .venv/bin/python scripts/apply_photo_order_patch.py"
```
`apply_photo_order_patch.py` 는 기본이 **미분류만 채움**(기존 순서 보존). 재분류로 덮어쓰려면 `--force`.

## 메모
- 데이터 파일(`data/…`: DB·몽타주·패치·results.json)은 git 제외. **코드/스크립트만** 커밋 대상.
- 이 분류는 비전 판독이 필요해 완전 자동화 불가 — 세션에서 이 루틴을 주기적으로(주 1회 등) 돌려 증분 처리한다.
- 저확신(confident=false)은 대개 건설장비·선박·전측컷만 있는 차량. 그래도 지도·서류는 맨 뒤로 정렬되므로 반영해도 안전.
