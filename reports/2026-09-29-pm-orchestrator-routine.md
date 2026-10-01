---
order: 2026-09-29-02
from: pm-orchestrator
ticket: 2026-09-29-02
result: done
verified: 재현
handoff:
  - to: qa-engineer
    why: PANEL-50 (2026-09-28 배분이 순환계 키 충돌로 유실) — test_dashboard_link_parity 버킷 건수를 절대값으로 고정, 분류를 틀어 우는지 반증, '== _list_count'·'== service.' 동어반복 전수. REC-8·REC-9 작업 트리 커밋 뒤 착수
  - to: backend-engineer
    why: org_runtime.py 인계 키 수정 — key 에 인계 순번(또는 why 해시)을 넣어 같은 보고서·같은 자리의 두 번째 인계가 조용히 버려지지 않게 하고, 건너뛸 때는 handoff.skipped 를 남긴다. 같은 자리 인계 2건 → 지시서 2장 확인 테스트 1건 포함
---
# PM 정기 점검 (2026-10-01 당직 실행)

**결론**: 반려할 보고서는 없다. 3일 넘게 열린 지시서가 13장(모두 09-27 발행, 4일째)이고, 순환계가 인계 1건(PANEL-50)을 조용히 버린 결함을 찾았다.
편집·호출·커밋은 하지 않았다.

## 1. 정체 지시서 (정체 기준 3일 초과)

| 번호 | 담당 | 상태 | 판단 | 검증 |
|---|---|---|---|---|
| 2026-09-27-15 | frontend-engineer | open | 선행 조건(REC-1)이 풀렸다(`bb9ef47`·`eefc578`). `자동: 아니오` 자리라 오너 세션에서 처리 | 재현(PM) |
| 2026-09-27-17 | backend-engineer | open | QA-1 백로그 상태가 아직 `todo`. 오너 세션 대기 | 재현(PM) |
| 2026-09-27-38 | backend-engineer | open | AUD-02 설계안 대기. 왕복 상한 경보 27-49 는 cancelled 인데 38 은 열려 있다 | 머리말은 재현(PM). **설계안이 실제로 없는지는 미검증** |
| 2026-09-27-57 | frontend-engineer | open | 29-04(KCAR-4)와 일부만 겹친다. F1(차익 카드)은 29-04 와 같고 F2(저장 입찰가 경고 = KCAR-3)는 29-04 에 없다. **통째로 취소하면 KCAR-3 화면 작업이 사라진다** — F2 만 남기고 29-05(PANEL-22) 뒤로 미루기를 권고 | status 는 당직 재현, 범위 비교는 PM 재현 |
| 2026-09-27-56 | pm-orchestrator | blocked | 닫아도 된다. 막힌 원인(백로그 쓰기 거부)은 29-03(done)이 KCAR-3·4·5·DES-6 을 백로그에 옮겨 해소됐다 | 당직 재현(27-56 `blocked`, 29-03 `done`) |
| 2026-09-27-39 | insight | blocked | 후속 30-15(steward)가 있다. AUD-07 은 **10-08 종결 강제 전환**, 권한 결정 시한 **10-05** | 재현(PM) |
| 27-18·19·40·41·46·55·61 | steward | open | 결재함 — 오너 결정 대기 | 재현(PM) |

별도 시한: **2026-09-30-18** — `min_refresh_daily_cap` 150→60 설정 변경·배포를 **10-02까지** 해야 한다. 배포는 오너 승인 사항이며 이미 결재함에 있다(당직 재현: `status: open`).

## 2. 미배분 todo 티켓

같은 목적의 지시서 2026-09-30-14(pm-orchestrator, open)가 따로 있다. 티켓 선정은 그쪽에 맡겼다.
이번 점검에서 새로 찾은 결함은 아래 하나다.

**PANEL-50 배분 유실 — 당직 재현.**
- `tools/org_runtime.py` 의 인계 키가 `key = f"handoff:{rel}>{to}"` 이고 바로 뒤에 `if has_key(key): continue` 가 있다. 그래서 한 보고서에서 같은 자리로 두 번째 인계를 적으면 **아무 기록 없이** 건너뛴다.
- `reports/2026-09-28-pm-orchestrator-unassigned.md` 의 handoff 에는 `to: qa-engineer` 가 두 번 있다(TEST-1, PANEL-50). 지시서는 TEST-1(2026-09-30-11, open) 하나만 생겼다.
- `orders/` 에서 PANEL-50 이 나오는 파일은 27-03·28-01·30-14 셋뿐이고, 모두 PANEL-50 을 맡긴 지시서가 아니다.
- PM 은 `data/org-bus.jsonl` 에 PANEL-50 이 0건이라고 했다. 당직은 이 부분을 따로 확인하지 않았다(미검증).
- 09-30-13 이 짚은 결함(ticket 칸에 주문번호가 들어감)과는 **다른 결함**이다.

이 보고서의 handoff 는 결함을 피하려고 **자리마다 한 건씩만** 적었다.

## 3. 반려 판정 대상

없다. `result: fail`·`blocked` 인데 `handoff: []` 인 보고서는 다섯 건이고, 모두 후속 회차가 나가 닫혔다(ux8-qa → 27-09·10·42 done · ops3-qa → OPS-3 완료 · ops4-qa → 27-69~77 · rec1fix-qa-r2/r3 → r4(30-08) done). PM 이 지시서 머리말로 대조했다. 당직은 다시 확인하지 않았다.

## 4. Steward 결재함으로 올릴 것 (handoff 가 아니라 본문에만 적음)

PM 은 `to: steward` 인계도 제안했다. 하지만 steward 는 org-contracts §2 pm-orchestrator 행의 '넘길 수 있는 곳'에 없어서 handoff 에서 뺐다. 내용만 옮긴다:
- 27-56 닫기(29-03 으로 해소됨)
- 27-57 은 F1 을 29-04 로 합치고, F2(KCAR-3)만 남겨 29-05 뒤로 미루기
- 오너 세션 대기 3장의 처리 순서 결정: 27-15 PANEL-20 · 27-17 QA-1 · 27-38 AUD-02
- **30-18 cap 150→60 은 10-02까지**, **AUD-07 권한 결정은 10-05까지**

## 검증 구분
- **당직 재현**: 인계 키 코드, 28 보고서의 qa-engineer 이중 인계, orders/ 의 PANEL-50 분포, 27-56·29-03·27-57·30-11·30-18 의 status
- **PM 재현(당직 재확인 안 함)**: 백로그 행(QA-1·AUD-07·KCAR-3~5), 27-57과 29-04의 범위 비교, 반려 대상 5건의 후속, org-bus 0건
- **미검증**: 27-38 AUD-02 설계안이 실제로 없는지
