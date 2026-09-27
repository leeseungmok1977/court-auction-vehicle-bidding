---
order: 2026-09-27-03
from: pm-orchestrator
ticket: 2026-09-27-03
result: done
verified: 재현
handoff:
  - to: frontend-engineer
    why: PANEL-20 — report.html 의 '상한선' 문장마다 기준 명사·금액을 박는다(템플릿+service.py 사용자 문자열 전수). before/after 캡처(md5 상이·기준 커밋 병기) 후 app-design-expert·design-critic 교차검수로 넘긴다
  - to: insight
    why: PANEL-09 1단계(코드 무변경) — 기존 DB(기일내역 유찰+sale_results)로 낙찰확률 분모를 만들 수 있는지, 유찰 층별 무입찰 비율(표본수 병기)·PANEL-17 선택편향 방향·새 외부요청 필요 여부를 쿼리 원문과 함께 보고
  - to: backend-engineer
    why: QA-1 — /api/vehicles/count 가 promising 을 받고 upcoming 음수를 0으로 클램프하게 하고, strict xfail 2건을 정상 테스트로 전환해 pytest 전체 통과. UX-8 커밋 뒤 착수
  - to: steward
    why: §4 — 닫기 후보 13건 백로그 상태 칸 정리(DoD 원문 대조), 110% 하드코딩 문구의 PANEL-08 연동, PANEL-05 nginx 헤더(오너 승인·ssh), PANEL-09 2단계 착수 전 보고
---

# 미배분 백로그 트리아지 — 2026-09-27 (지시서 2026-09-27-03)

> 작성: 당직 Steward가 `pm-orchestrator` 결과를 옮겨 적음. 서브에이전트는 읽기만 했음(코드·DB 쓰기·외부요청·위임 0).
> 기준 HEAD `c7d38d0`, 작업 트리에 UX-8 미커밋 변경(`vehicles.html`·`app.css`·테스트 5파일) 있음.
> `steward` 인계는 서브에이전트 §4 "오너 결정 / Steward 조치가 필요한 항목"을 옮긴 것이다.

[요약] 이번 주 착수 3건: **PANEL-20**(리포트 금액 오독) · **PANEL-09 1단계**(7회 반복 지적, 입찰을 과다 쪽으로 미는 편향 — 근거 산출만) · **QA-1**(저장 검색 건수 불일치).
48건 중 **13건은 본문엔 '완료'인데 상태 칸만 `todo`** — 미배분 수가 부풀려져 있다.

## 0. Steward 재현 결과 (운영 규칙 5)

| 주장 | 확인 방법 | 판정 |
|---|---|---|
| PANEL-20: `report.html` 한 `v-sub` 에 `재판매 상한가 {{ upper }}` 바로 뒤로 `예상 경쟁가가 상한선을 {{ (exp - max_bid) }}원 넘습니다` 가 붙는다 — 앞 명사(재판매 상한가)와 뺄셈 대상(`max_bid`)이 다르다 | Read — 앵커 `예상 경쟁가가 상한선을 {{ (exp - max_bid)|won }}` | **재현(코드)** |
| 같은 계열: `sp-blabel` "상한선을 N만원 초과", `detail.html` `_over` "현 최저매각가가 상한선을 N% 초과" | Grep `상한선을` | **재현(코드)** |
| QA-1: `def vehicles_count(` 서명에 `promising` 없음, `up = int(upcoming)…` 뒤 `if up < 0` 클램프 없음(`/vehicles` 쪽엔 있음) | Read `web/app.py` | **재현(코드)** |
| QA-1: xfail `test_known_gap_count_api_ignores_promising`·`…_negative_upcoming` 실재 | Grep | **재현(코드)** |
| PANEL-09: `win_probability` 독스트링이 분모 누락("유찰 615건이 있으나 … 같은 모집단이 아니다")을 스스로 적음 | Grep `web/service.py` | **재현(코드)** |
| 유찰 615건 · 저장검색 372 vs 1,163건 · PANEL-20 라이브 재현(`2026타경70210_1`) | DB·라이브 조회 안 함 | **미검증** |
| 닫기 후보 13건 · 부분완료 4건 · 대기 사유 각 줄의 Grep 근거 | 서브에이전트 Grep 인용. Steward는 개별 재현 안 함 | **미검증** |
| `report.html` "소매 시세의 110%(소프트캡)" 하드코딩 문구 | Read (앵커 `소매 시세의 110%(소프트캡)`) — 1곳 확인. 서브에이전트는 "두 곳" 주장 | **1곳 재현 · 2곳째 미검증** |

## 1. 선정 3건

| 티켓 | 담당 | 완료 기준(DoD, 백로그 원문과 대조) | 선정 근거 |
|---|---|---|---|
| **PANEL-20** 리포트 §01 '상한' 오독 | `frontend-engineer` → `app-design-expert`+`design-critic` 교차검수 | 원문: "**`상한선` 이 나오는 모든 자리에 기준 명사를 박는다**(예: '손익분기(890만원)를 500,000원 넘습니다'). 고친 뒤 같은 물건으로 다시 받아 세 문장 나란히 읽어 확인, 두 자리 교차검수." + ① 범위 = 템플릿·`web/service.py` 사용자 문자열·툴팁 전수(PANEL-36·47 교훈) ② 대상 물건은 DB에서 `bidst.state=='over_market'` 이고 `exp > max_bid` 인 것을 골라 적는다(공허 통과 방지) ③ 6폭 넘침 0, 큰글씨 ON/OFF ④ before/after md5 상이, 기준 커밋 기록 ⑤ 렌더 테스트 + 사보타주로 실패 확인 | 금전 오독 최대(50만원 차이를 438만원으로 읽을 수 있음). 숫자 표기 = 교차검수 대상. `report.html` 만 건드려 UX-8(`vehicles.html`)과 충돌 없음 |
| **PANEL-09** 낙찰확률 분모 — **1단계(근거 산출)만** | `insight` (자동: 예) | 원문 DoD("수집 시 유찰 기일도 기록하는 스키마 변경")는 이번 주에 **닫지 않는다.** 1단계 산출: ① 기일내역 유찰과 `sale_results` 가 같은 모집단으로 합쳐지는지, 몇 건인지 ② 합쳐지면 무입찰 비율(유찰 0~1·2·3회+ 층별, 표본수·조건 병기) ③ PANEL-17 비무작위 표본에서 남는 편향 방향 ④ `auction_result='유찰'` 이 일일 갱신에서 이미 관측되는지 = 새 외부요청 없이 저장만 하면 되는가 ⑤ 사실/추정 구분·쿼리 원문 | 7회 연속 지적(`docs/reviews/2026-09-12-r5.md`·`2026-09-22.md`·`2026-09-23.md`). 편향이 사용자를 더 높이 쓰게 미는 방향이다. frontend·backend가 막혀 있어도 insight는 지금 진행 가능. PANEL-53(170건 공백) 원인도 함께 드러날 수 있음(추정) |
| **QA-1** `/api/vehicles/count` 패리티 틈 2개 | `backend-engineer` | 원문: "두 파라미터를 `/vehicles` 와 같은 규칙으로 받고, strict xfail 2건(`test_known_gap_count_api_*`)을 정상 테스트로 전환." + ① 운영 사본에서 `promising=1`·`upcoming=-5` 둘 다 목록 총수 = API 총수 ② 전체 pytest 통과(`NC_NO_SCHEDULER=1`) ③ `sale_results` `count(*)`·`max(recorded_at)` 불변 ④ **UX-8 커밋 이후 착수**(같은 테스트 파일에 미커밋 +11줄) | 즐겨찾기 저장 검색에 가짜 '새 매물'이 뜬다 = 신뢰 문제. 테스트가 준비돼 있어 작업이 작다 |

## 2. 나머지 45건 — 대기 사유 (미검증: 서브에이전트 인용)

**닫기 후보 13건** — 본문·코드는 완료인데 상태 칸만 `todo`:
PANEL-26(제목이 이미 `실측 검증`) · PANEL-29(`cf5b6d1`, `web/` 에 `* 1.10` 0건) · PANEL-34(본문 "전수 점검 완료 — 닫는다") · PANEL-35(`ff87396`) · PANEL-36(`cf5b6d1`) · PANEL-37(`ff87396`) · PANEL-39(`8dcf4f9`, 반증 1→12 failed) · PANEL-40(`bbcb8c1`) · PANEL-41(`c171e3b`) · PANEL-42(`c171e3b`+CLAUDE.md 규칙 8) · PANEL-43(`c171e3b` 판정 완료) · PANEL-44(본문 "코드 변경 없이 닫는다") · PANEL-46(`412e906`, 후속 50·51·52로 분리됨)

**부분 완료·병합**
- PANEL-38·PANEL-45: SOP는 완료. 남은 것은 캡처 도구 자동화(같은 해시면 실패 + 기준 커밋 자동 기록)라 **한 티켓으로 병합** 제안(`tools/store_final.py` 의 `HEAD.json` 선례)
- PANEL-28: ⑴⑶ 완료, ⑵ 정확도 표기만 남음 → PANEL-32와 묶음
- IMP-R2-04: DoD 검증 수단이 없음 → PANEL-28⑵·32에 흡수하고 닫는 안

**UX-8 선결(`vehicles.html` 충돌·재측정 필요)**: PANEL-27 · PANEL-31 · QA-2 · QA-3(경미) · DES-1(교차검수) · DES-2 · DES-3(⚠ UX-8이 접힌 머리를 기본으로 만들면 노출이 늘 수 있음 — UX-8 검수 범위에 320 큰글씨+날짜/가격대 첫 부품 조합을 넣을 것, 추정)

**frontend 대기**: PANEL-32(다음 주 1순위 후보, `여유` 는 None/0 구분 필요 = 금액 인접) · PANEL-33(`detail.html` 2곳 + **`calendar.html` 세 번째 자리 발견** → 범위 확장 필요) · PANEL-47(`acc_why()` 층 열거, 층 추가 계획 없어 급하지 않음) · PANEL-48(접근성) · PANEL-57(검수 의견 갈림, 판단 보류) · PANEL-61(`<!--` 84곳, 빌드 단계 결정 필요) · PANEL-06(관리자 전용 확정, 최하)

**백엔드·데이터·절차**
- PANEL-63: `침수의심` 이 전손차에도 붙는 사실 오기. 다음 주 후보(교차검수 자리가 UX-8에 묶여 있음)
- PANEL-64: PANEL-62와 묶음
- PANEL-53: PANEL-09 1단계 조사에 원인 조사를 포함하는 안
- PANEL-59: 파싱 누락인지 원자료 부재인지 모름. 외부요청이 필요하면 C.4 승인 지점
- PANEL-19: 배너는 `encar_health.degraded` 때만 렌더 → 현재 노출 0. KCAR-1과 묶음
- PANEL-18: `REUSE_PLATFORM` 경로 전용 컬럼이라 사용자 노출 없음
- PANEL-49: 개발 도구 cp949 문제. QA-1 다음 backend 슬롯
- PANEL-51: 영향 0.49%(7건)
- PANEL-50·PANEL-52: qa 주간 게이트(자동: 예)에 묶어서 처리
- PANEL-23: CLAUDE.md 측정 규칙 한 줄 → Steward 절차
- DATA-01: 사용자에게 보이는 결함 없음, 마이그레이션 필요
- DATA-03: **blocked** — 대법원 응답에 물건 귀속 정보가 있는지 `capture/` 가 필요함(C.4-3, 사람 입력)
- PANEL-05: **오너 승인** — 헤더가 서버 nginx에 있어 ssh·배포 필요

## 3. 인계 메모
- `frontend-engineer`·`backend-engineer` 는 `자동: 아니오` → 당직은 부르지 않는다. **오너가 연 세션**에서 집행한다. backend(QA-1)는 KCAR-1 검토(-12)·UX-8 커밋 뒤에 한다.
- `insight` 는 `자동: 예` → 순환계가 지시서를 만들면 당직이 부를 수 있다. Write 권한이 없어 보고서는 Steward가 대신 쓴다.

## 4. Steward·오너 결재 항목 (→ `steward`)
1. **[Steward 자율]** 닫기 후보 13건의 상태 칸 정리. 반드시 DoD 원문과 대조한 뒤 닫는다(운영 규칙 7). 서브에이전트는 일부러 닫지 않았다. 정리하면 미배분이 약 48건에서 33건으로 준다.
2. **[오너 · PANEL-08 연동]** `report.html` 의 "소매 시세의 110%(소프트캡)" 하드코딩 문구. PANEL-08 권고값(1.00)을 승인하면 이 문장이 거짓이 된다 → 값 승인과 같은 배치에서 문구를 `soft_cap_ratio()` 에 연결할 것.
3. **[오너]** PANEL-05 권고: `Permissions-Policy` 먼저 켜고, CSP는 Report-Only로 시작. ssh·배포 사항이다.
4. **[오너 · 나중]** PANEL-09 2단계에서 산식을 보정하면 화면의 낙찰확률이 **오른다** — 입찰 판단에 직접 영향을 주므로 착수 전에 오너에게 보고한다.
