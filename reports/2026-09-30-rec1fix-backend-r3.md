---
order: 2026-09-30-01
from: backend-engineer
ticket: REC-1
result: done
verified: 재현
handoff: []
workflow: rec1fix-r3
---

# REC-1 3회차 — qa N1·N2 수정 + REC-7 ⑹ 사실 대조

- N1: 오늘의 추천 캐시 경로에 판정 게이트를 건다.
- N2: 차단 예외가 기록 실패에 가려지지 않게 한다.
- REC-7 ⑹: 설명 행 ④ 사유별 문장을 service 사실과 대조한다.

> 지시서 2026-09-30-01. 저장소 HEAD 8073a3d 와 1·2회차 미커밋 변경(작업 트리) 위에서 작업했다.
> - 커밋·배포·ssh·외부 요청은 0 이다. 운영 8765(PID 94908)와 운영 data/ 는 건드리지 않았다.
> - 백업 `data/backups/auction-20260929.db.gz`(md5 492e86ac)는 읽기만 해서 scratch 에 풀었다. 결과 md5 는 e9a5bc43 으로 1·2회차와 같다.
> - 재등급 적용 사본은 qa 2회차 scratch 의 d_apply(44a3f8d3)를 복사해 썼다.
> - 판정 기준 값(config margin·risk·사고 가정·게이트)은 바꾸지 않았다. config.yaml md5 8b3f1319 로 2회차 판과 같다.
> - **app.py·템플릿은 한 줄도 고치지 않았다**(frontend 동시 작업). 내 변경 파일은 `web/service.py` 와 새 테스트 `tests/test_rec1_r3_picks_gate_block.py` 둘뿐이다.
> - 지시서 output 은 `reports/2026-09-30-backend-engineer-REC-1-r4.md`, 하네스 경로는 `reports/2026-09-30-rec1fix-backend-r3.md` 다.
>   이 본문은 하네스 규칙상 내가 파일로 쓰지 않았다. 하네스 경로에 저장해 달라.

## [요약]
**N1 을 고쳤다(확인).**
- `get_daily_picks` 캐시 경로와 `compute_daily_picks` 계산 경로가 이제 **같은 자격 함수** `_daily_pick_gate` 를 부른다.
- 09-29 사본에 저장된 추천(520d·E300 resale)을 새 코드로 같은 날 읽으면 두 차가 빠진다. 09:00·12:00·22:30, 재등급 전·후 모두 같다.
  - 전(2회차 코드): 캐시 경로 4장 중 2장이 '되팔아도 남음'이면서 예상낙찰가가 None 이다.
  - 후: 2장(12604_1·30698_1)만 남는다. 둘 다 실사용 now 칸이고 예상낙찰가가 있다.
- 계산 경로 결과는 전후 같다(5장).
- 캐시 경로 누수가 두 번째라는 사실을 주석 두 곳에 남겼다.

**N2 를 고쳤다(확인).**
- `refresh_lagged_floors` 의 finally 에서 `last_min_refresh` 기록이 실패해도, 올라가던 차단 예외가 그대로 올라간다. 대상은 403·429·warmup HTTPError(403)·비정상 3연속이다.
- 기록 실패는 로그(`naechaget.floor_refresh` WARNING)로만 남긴다.
- 올라갈 예외가 없을 때만 기록 실패를 올린다. 2회차와 같은 동작이다.
- qa 적대 테스트 2개를 이름 그대로 저장소로 옮겼고 초록이다. qa 원본 scratch 파일 7개도 지금 트리에서 7 passed 다(2회차는 5 passed · 2 failed).

**REC-7 ⑹(설명 행 ④ 사유별) — backend 코드 변경은 없다.**
- frontend 가 app.py 에 만든 `_floor_hold`·`FLOOR_HOLD_MSG` 를 service 사실과 대조했다.
- 가드 240대 전수를 '최저가가 확인됐다'고 놓고 다시 계산했다(반사실 계산).
  - 문장-사실 불일치: 0.
  - 입찰 전 가드의 bid_state 라벨과 사유 분류 불일치: 0.

**테스트**
- 새 테스트는 12개다. 2회차 코드에서는 이 중 9개가 빨갛다.
- 변이 14종이 전부 KILLED 다.
- 격리 트리 전체 스위트는 **2,548 passed · 5 xfailed · 0 failed** 다. 2회차 2,536 에 새 12개를 더한 수다.
- 작업 트리 전체 스위트는 1 failed · 2,547 passed · 5 xfailed 다.
  - 실패 1건은 frontend 가 작업 중이던 템플릿에서 나왔다.
  - frontend 의 다음 판에서 다시 돌리면 통과한다(§4).

**스키마 변경은 없다**(DB·config·템플릿 컨텍스트 키). 바뀐 것은 두 가지다(§5).
- 캐시 경로가 돌려주는 카드 수: 자격 미달 저장분이 빠진다.
- 기록 실패 시 올라오는 예외 종류.

## 1. N1 — 오늘의 추천 캐시 경로

### 1.1 재현 (확인 — scratch, 외부 요청 0)
**조건**
- 09-29 사본(e9a5bc43)과 재등급 적용 사본(44a3f8d3)을 썼다.
- settings 는 `daily_picks_date=2026-09-29` 이다. 저장 순서는 [30118_1 resale · 12604_1 now · 50522_1 resale · 30698_1 now · 70425_1 now]로, 옛 코드가 그날 저장한 것이다.
- 시각은 2026-09-29 09:00·12:00·22:30 으로 고정했다. 대상은 service.date·datetime, datetime 모듈, SQL date('now') 다.
- 루프백 밖 connect·DNS 는 차단하고 기록했다. 시도는 0 이다.
- 실행 전후 DB md5 가 같다. 캐시 경로는 쓰지 않는다.

**저장된 다섯 장의 지금 상태**(12:00, 재등급 전)

| 물건 | 저장 칸 | 저장 판정 | 최저가 | 예상낙찰가 | bid_state |
|---|---|---|---|---|---|
| 30118_1 BMW 520d(10-12) | resale | 입찰 검토 가능 | 미확인(가드) | 없음 | wait '다음 기일 최저가 공고 대기' |
| 12604_1 콰트로포르테(09-30) | now | 유찰 대기 | 확인 | 16,800,000 | usepick '지금 사면 이득' |
| 50522_1 벤츠 E300 4Matic(10-12) | resale | 입찰 검토 가능 | 미확인(가드) | 없음 | wait(같음) |
| 30698_1 G80(10-08) | now | 유찰 대기 | 확인 | 7,800,000 | usepick |
| 70425_1 스포티지(09-29 10:30) | now | 유찰 대기 | 미확인 | 없음 | wait '기일 경과 — 결과 확인 전' |

**결과**

| DB · 시각 | 2회차 코드(service 496dd794) 캐시 경로 | 3회차 코드 캐시 경로 |
|---|---|---|
| 09-29 사본 · 09:00·12:00·22:30 | 30118_1 resale(예상 없음) · 12604_1 · 50522_1 resale(예상 없음) · 30698_1 | 12604_1 now · 30698_1 now |
| 재등급 적용 사본 · 22:30 | 12604_1 · 50522_1 resale(예상 없음) · 30698_1 — qa 캡처와 같음 | 12604_1 · 30698_1 |
| 재등급 적용 사본 · 12:00 | (재지 않음) | 12604_1 · 30698_1 |

- 계산 경로(`compute_daily_picks`)는 두 코드·모든 조건에서 같다: 12604_1 now · 30698_1 now · 20278_1 cheap · 34491_1 cheap · 31035_1 now.
- 70425_1 은 전후 모두 빠진다. 가드라 실사용 갈래가 없기 때문이다(qa 관찰과 같다).

### 1.2 무엇을 바꿨나 (`web/service.py`)
**`_daily_pick_gate(v, kind, bt, tier=None) -> (예상낙찰가, 시세) | None`(신규)**
- 계산 경로 `_add` 에 있던 자격을 그대로 옮겼다.
  1. 사진·시세·최저매각가가 있다.
  2. `_promising` 이다(신뢰도 '높음', 오매칭 아님).
  3. bid_state tone 이 stop 이 아니다.
  4. **예상낙찰가와 시세가 있다.** floor_unconfirmed 이면 `expected_for` 가 None 이라 여기서 빠진다.
  5. 칸이 맞는다. resale 은 judgment '입찰 검토 가능'(후보 조건)이고, now·cheap 은 `personal_use_tier` 의 갈래가 같아야 한다.
- 저장 문자열만으로 카드 판정을 정하지 않는다. judgment 는 재판매 칸의 후보 조건일 뿐이다. 그 값도 옛 최저가로 매긴 것일 수 있다.

**두 경로**
- `compute_daily_picks._add` 는 이 함수를 부른다. 동작은 같다. 실사용 갈래는 이미 계산한 tier 를 넘겨 다시 계산하지 않는다.
- `get_daily_picks` 캐시 경로는 stop 한 줄과 judgment 문자열·tier 재확인을 지우고 **같은 함수**를 부른다.
  - 날짜·입찰 시각·낙찰/종결·상세없음 게이트는 그대로 둔다.

**주석**
- 캐시 경로 누수는 두 번이다.
  1. 2026-09-22 시동 불가 카니발 — 그때는 stop 한 줄만 더했다.
  2. 2026-09-29 N1.
- 그래서 한 줄을 더 얹지 않고 자격을 한 함수로 모았다고 적었다(`get_daily_picks` 본문, `_daily_pick_gate` docstring).
- `get_daily_picks` docstring 의 '여전히 유효(검토가능·미래기일)'도 새 조건에 맞게 고쳤다.

**조이기만 했다.**
- 캐시 경로에 사진·신뢰도·예상낙찰가 조건이 새로 붙었다(실사용 칸 포함).
- 푸는 조건은 없다.

### 1.3 실데이터 등식 (확인)
- 09-29 사본에서 입찰예정 417대 × 3칸(resale·now·cheap), 모두 1,251 조합을 저장해 캐시 경로로 읽었다.
- 통과한 것은 계산 경로 후보 5개와 **정확히 같다**(09:00·22:30). 계산 쪽에만 있는 것 0, 캐시 쪽에만 있는 것 0.

### 1.4 배포 당일 — 알고 있어야 할 것
**빈 자리는 채우지 않는다.**
- 저장 추천은 하루를 버틴다. 이 수정으로 가드 카드는 빠지지만 빈 자리를 **채우지 않는다.**
- 09-29 조건이면 홈 캐러셀은 그날 자정까지 2장이다. 새로 계산하면 5장이다.
- 5장으로 돌리려면 배포 직후 추천을 다시 계산하면 된다(qa N1 처방 ②).
  - 방법: `service.refresh_daily_picks(5)` 를 부르거나, settings `daily_picks_date` 를 초기화한다. 초기화하면 다음 홈 요청이 계산한다.
- 이것은 서버 DB 에 쓰는 운영 조작이라 하지 않았다. 배포 창에서 Steward·오너가 정할 일이다. 하지 않아도 거짓 카드는 없다.

**홈 요청마다 부르는 함수라 시간을 쟀다.**
- 조건: 5장 저장, 30회 반복.
- median 71.7ms(2회차 코드, 4장 반환) → 64.8ms(3회차, 2장 반환).
- 전체 스위트와 동시에 돈 측정이라 잡음이 크다. '퇴행 없음' 정도로만 읽는다.

### 1.5 남은 틈 — 이번에 고치지 않음(범위 밖, 후속 후보)
**1. 재판매 칸과 '지금 입찰 추천' 칸의 기준 차이**(확인, 지금 영향 0)
- '지금 입찰 추천'(review 버킷)은 judgment + bid_state state ∈ {resale, usepick} 이다.
- 캐러셀 재판매 칸은 judgment + tone≠stop + 예상낙찰가다.
- 그래서 bid_state 가 '예상 경쟁가가 상한선 초과'(caution)나 '손익분기 산출 불가'인 재판매 후보는 캐러셀에서 '✓ 되팔아도 남음'이 될 수 있다. 그런데 '지금 입찰 추천' 수에는 없다.
- 09-29 사본에서 판정 '입찰 검토 가능'은 5행이다(usepick 3 · 가드 wait 2). 게이트를 통과한 재판매 후보는 0 이라 지금 영향은 0 이다.
- 이것을 막으려면 계산 경로의 선정 기준을 바꿔야 한다. 그래서 이번에는 '_add 와 같은 게이트' 지시 그대로 두었다.

**2. 홈 '임박 매각기일 · 검토가능' 알림과 헤더 벨도 저장 문자열 judgment 만 본다**(코드 확인, 지금 영향 0, 앞으로는 추정)
- 해당 함수: `alert_items`(알림)·`alert_count`(헤더 벨).
- 09-29 09:00 의 3일 창은 1대이고 가드가 아니다.
- 14일 창으로 넓히면 5대 중 520d·E300 이 가드다(예상낙찰가 None).
- E300 은 판정·가드가 그대로면 10-09 부터 3일 창에 들어온다(추정). 그러면 '검토가능 물건' 카드에 예상낙찰가 '—'가 뜬다.
- 벨 배지와 카드 수가 같아야 한다는 테스트가 있는 곳이라 둘을 함께 바꿔야 한다. 티켓으로 만들기를 권한다.

## 2. N2 — 차단 뒤 기록 실패가 차단을 가리던 것

### 2.1 원인 (확인)
- 파이썬에서는 finally 에서 난 예외가 올라가던 예외를 대신한다.
- 2회차 `refresh_lagged_floors` 는 finally 에서 `db.set_setting("last_min_refresh", …)` 를 가드 없이 불렀다.
- 차단이 난 순간 이 기록이 OperationalError 로 실패하면, 그 예외가 차단 예외 대신 올라갔다.
  - 차단 경로는 둘이다: fetch 403(RuntimeError → stop_err), warmup HTTPError(403)(except 에서 다시 올림).
- daily_update 는 이 예외를 RuntimeError 도 `_is_block` 도 아니라고 보고 격리했다. 그래서 낙찰결과·최종 검토·출시가 단계로 계속 갔다.
- service.py 의 finally 10곳을 모두 봤다.
  - 락 해제 5
  - `conn.close()` 3
  - 케이카 세션 close 1(이미 try/except)
  - 설정 기록 1(이곳)
- 외부 요청 경로에서 finally 안에 DB 쓰기가 있는 곳은 이 한 곳뿐이다.

### 2.2 무엇을 바꿨나
**finally 의 기록을 try/except 로 감쌌다.** 실패는 `save_err` 로 잡아 둔다.
- 올라가던 예외가 있으면 그것이 그대로 올라간다. 대상은 except 의 재발생과 stop_err 다.
  - 이때 기록 실패는 `naechaget.floor_refresh` WARNING 한 줄로만 남긴다.
  - 로그 문구: `last_min_refresh 기록 실패(OperationalError: …) — 올라가던 예외를 그대로 올린다(stopped=…)`
- 올라갈 예외가 없을 때만 finally 뒤에서 기록 실패를 올린다. 2회차와 같은 동작이고, 호출자가 비차단 오류로 격리한다.
- 우선순위: 올라가던 예외 > stop_err(차단·3연속) > 기록 실패.

**그 밖에**
- '올라가는 중'을 빠짐없이 표시하려고 `except BaseException`(KeyboardInterrupt 등)도 추가했다. 표시만 하고 그대로 다시 올린다. stopped 기록 방식은 그대로다.
- docstring 에 한 줄을 더했다: 기록이 실패해도 차단·3연속 예외를 가리지 않는다.

**C.4 유지** — 아래는 한 글자도 바꾸지 않았다.
- 요청 간 5~10초 지연
- 하드캡 150
- 재시도 없음
- 차단 즉시 중단
- 비정상 3연속 중단
- daily_update 의 격리 조건(`RuntimeError or _is_block` 은 전파)

### 2.3 확인한 동작 (테스트, 외부 요청 0)
- 기록 실패는 `db.set_setting("last_min_refresh")` 만 OperationalError 로 만들어 흉내 냈다.
- 모두 재조회를 켠 상태다.

| 상황 | 2회차 코드 | 3회차 코드 |
|---|---|---|
| fetch 403 + 기록 실패 | OperationalError → 격리, 뒤 단계 계속 | RuntimeError('…차단 감지…') 전파 · 요청 1 · 뒤 단계 0 · WARNING 1 |
| warmup HTTPError(403) + 기록 실패 | 같음(계속) | HTTPError(403) 전파 · 뒤 단계 0 · WARNING 1 |
| fetch ConnectionError 3연속 + 기록 실패 | OperationalError → 계속 | RuntimeError('…3회 연속…') · 요청 3 · 뒤 단계 0 |
| 직접 호출(maint floor-refresh 자리) 429 + 기록 실패 | OperationalError | RuntimeError('차단') · 요청 1 |
| warmup ConnectionError(비차단) + 기록 실패 | OperationalError 로 격리 — 메시지가 원인을 틀리게 말함 | ConnectionError 로 격리 · '⚠최저가 재조회 오류 ConnectionError' |
| 정상 완료 + 기록 실패 | OperationalError 로 격리 | 같음(유지) · 반영한 최저가 6,860,000 남음 |

## 3. REC-7 ⑹ — 설명 행 ④ 사유별 (backend 몫 = 사실 대조)
**누가 무엇을 했나**
- 문장은 frontend 가 app.py 에 만들었다: `_floor_hold`(분류)와 `FLOOR_HOLD_MSG`(문장). 대조 시점 app.py md5 는 fb9d2b8d 다.
- backend 는 새 키·새 함수를 주지 않았다. 같은 개념을 두 곳에 두지 않는다는 2회차 방침 그대로다. service 로 옮기는 일은 REC-7 ⑴이다.

**대조 방법**
- 대상: 09-29 사본의 입찰예정 417대 중 가드 240대.
- 물건마다 '이번 회차 최저가가 확인됐다'고 놓았다. 기일내역에 이번 매각기일 행을 더하고, 최저가를 한 단계 이상 저감했다.
- 그 상태에서 `expected_for`·`bid_state` 를 다시 돌렸다.
- 판정 보류가 풀리는지는 기일을 미래로 옮겨서 봤다. 기일 분기가 가로채지 않게 하려는 것이다. 사유 자체는 기일과 무관하다.

| `_floor_hold` | 가드(09:00) | 입찰 전(22:30) | 확인 뒤 예상낙찰가 | 확인 뒤 판정 | 화면 문장 | 사실과 |
|---|---|---|---|---|---|---|
| 없음(최저가만) | 162 | 136 | 162/162 나옴 | 풀림(09:00: usepick 88 · blocked 39 · over_market 29 · resale 6) | ④ 원문 '확인 전까지 예상낙찰가·추천 전략은 내지 않습니다' | 맞음 |
| lowconf(시세 있음·신뢰도 낮음) | 27 | 23 | 27/27 나옴 | 보류(lowconf) 27 | '시세 신뢰도가 낮아 판정은 보류됩니다' | 맞음 — '예상낙찰가를 내지 않는다'고 쓰면 27대에서 거짓 |
| nomed(시세 없음) | 32 | 27 | 0/32 | lowconf 32 | '시세가 산정되지 않아 예상낙찰가는 내지 않습니다' | 맞음 |
| nomarket | 10 | 9 | 0/10 | nomarket 10 | '동급 시세가 없어 예상낙찰가는 내지 않습니다' | 맞음 |
| stop(시동·운행 불가) | 9 | 7 | 4/9 | 보류(lowconf·stop) 9 | '시동·운행 불가라 판정은 보류됩니다' | 맞음 |
| flood | 0 | 0 | — | — | '침수·전손 의심이라 입찰 보류입니다' | 09-29 가드에 없음(렌더되지 않는 분기) |

- 입찰 전 가드(09:00 240대 · 22:30 202대)에서 bid_state 라벨과 `_floor_hold` 분류가 모두 맞는다(불일치 0).
  - 22:30 에 오늘 입찰이 끝난 38대는 라벨이 '기일 경과'라 대조 대상에서 뺐다.
- '없음 162'는 2회차 §4.2 의 'bid_state.max_bid 있음 162'와 같은 수다.
- 구조상 주의(추정): `no_market_reason` 은 모델 낱말로 정한다.
  - 그런 물건에 시세가 있으면, 최저가 확인 뒤 예상낙찰가가 나와 nomarket 문장이 틀린다. 09-29 에는 0대다(0/10).
  - bid_state 쪽은 `no_market_reason and not exp` 라서 이 경우를 스스로 풀어 준다.
  - 화면 분류와 bid_state 가 한 곳에 있어야 하는 이유다. REC-7 ⑴ 몫이다.

## 4. 테스트
### 4.1 새 파일 `tests/test_rec1_r3_picks_gate_block.py` — 12개
**외부 요청 가드**
- 루프백 밖 connect·connect_ex·DNS 와 service.new_session·warmup·fetch_detail 을 막는다.
- 시도를 기록하고, 테스트가 끝날 때 기록이 비었는지 본다.

**N1 6개**
1. 전제: 가드 두 대는 예상낙찰가 게이트 하나로만 갈린다. stop·신뢰도·사진 게이트는 통과하고, 대조군이 있다.
2. 계산 경로는 이미 거른다.
3. **N1 재현**: 저장분(520d·E300·대조군)을 읽으면 대조군만 남는다. 예상낙찰가 '—' 카드는 0장이고, 저장분은 바뀌지 않는다.
4. 옛 저장 형식(id 문자열)도 같은 게이트를 지난다.
5. **두 경로 등식**: 8대 × 3칸을 저장해 읽은 캐시 결과가 계산 결과와 같다.
   - 8대 구성: 가드 2 · stop · 신뢰도 보통 · 사진 없음 · 1회 지연 실사용 가드 · 대조군 2.
6. 구조: 두 경로 모두 `_daily_pick_gate(` 를 부르고, 캐시 경로에는 judgment 문자열 비교가 없다.
- 픽스처는 09-29 백업의 520d·E300 값을 그대로 썼다. 날짜만 오늘 기준으로 옮겼다.

**N2 6개**
- qa 원본 2개(이름 그대로). 옮기면서 예외 종류·요청 수·WARNING 로그까지 보도록 강화했다.
- 추가 4개: 3연속 · 직접 호출 429 · 비차단 원래 오류 · 정상 완료 유지.

### 4.2 반증
- 2회차 코드(service 496dd794, 나머지 2회차 판) scratch 트리에서 이 파일을 돌리면 **9 failed · 3 passed** 다.
  - 통과한 3개는 전제·계산 경로·정상 완료 유지다. 예전 동작을 고정하는 검사라 통과가 맞다.
- qa 원본 scratch 파일(7개)을 저장소 cwd 에서 지금 트리로 돌리면 7 passed 다(2회차 5 passed · 2 failed).
  - scratch cwd 에서 돌리면 config 상대 경로 때문에 5개가 FileNotFound 류로 실패한다. 코드가 아니라 실행 위치 문제다.

### 4.3 변이 14종 — 전부 KILLED
- scratch 복사 트리에서만 돌렸다. 변이 없는 기준선은 관련 6파일 149 passed 다.

| 묶음 | 넣은 변이 |
|---|---|
| N1 | 캐시 경로 옛 코드 복귀 · 캐시 게이트 제거 · 캐시에서 칸을 resale 로 고정 · 게이트 resale judgment 조건 제거 · tier 조건 제거 · `_promising` 제거 · 사진 조건 제거 · stop 조건 제거 · resale 만 예상낙찰가 면제 |
| N2 | finally 복귀(가드 없음) · 기록 실패 항상 삼킴 · 기록 실패를 stop_err 보다 먼저 · 올라가는 중 표시 누락(로그로 잡힘) · finally 안에서 재발생 |

### 4.4 관련 묶음 (작업 트리)
- 16파일 241 passed.
- 최종 service.py(d8a5866f, docstring 한 줄 차이)로 핵심 3파일 54 passed.
- frontend 의 새 `test_rec1_r3_view.py`(42d0522a)와 함께 돌린 5파일 141 passed.

### 4.5 전체 스위트

| 조건 | 결과 |
|---|---|
| **격리 트리** — 작업 트리 복사본에서 frontend 파일만 2회차 판으로 되돌림(구성은 아래) · 01:15~01:30 · 다른 실행 없음 | **2,548 passed · 5 xfailed · 0 failed**(906초) = 2회차 2,536 + 12 |
| **작업 트리 그대로** — frontend 작업 중, service 4137fa54(최종판과 docstring 만 다름) · 00:57~01:14 | 1 failed · 2,547 passed · 5 xfailed(1,044초) |

**격리 트리 구성**
- 복사에서 뺀 것: data · .git · node_modules · screenshots. 단 screenshots/store 는 넣었다.
- frontend 파일(app.py·템플릿 5)은 2회차 판이다: app 19d9a8e8 · detail 62efa4ba · report 20a023a8 · dashboard 4ad30544 · vehicles 6663c5f2 · watchlist HEAD b0631836.
- frontend 의 새 테스트 1개는 뺐다.
- service 는 최종판 d8a5866f 다.

**작업 트리 실패 1건**
- `tests/test_render_smoke.py::test_no_multichar_hangul_inside_monospace` 다.
- 그 시각 frontend 가 detail.html·dashboard.html 을 고치던 중이었다.
- 01:15 에 frontend 의 다음 판(detail 357e5f29 · dashboard 8448dff4)으로 단독 재실행하면 통과한다.
- 내 파일(service·새 테스트)은 템플릿을 건드리지 않는다.

## 5. 명세 — 스키마·API 변경 표 (frontend 반영 필요 없음)

| 구분 | 변경 | 하위호환 |
|---|---|---|
| DB | 없음 | — |
| config | 없음 | — |
| 템플릿 컨텍스트 | 없음 — `daily_picks` 원소 모양(`_pick_dict` + `pick_kind`) 그대로 | — |
| `get_daily_picks` 반환 | 모양은 같다. 자격 미달 저장분이 빠져 원소 수가 줄 수 있다(09-29 조건 4→2) | 예 |
| service 함수 | 신규 내부 함수 `_daily_pick_gate(v, kind, bt, tier=None)` | 예 |
| `refresh_lagged_floors` 예외 | 기록 실패 + 올라가던 예외 → **원래 예외**(전: OperationalError). 올라갈 예외 없음 + 기록 실패 → OperationalError(전과 같음) | 예 — 차단이 더 확실히 멈춘다 |
| 실행 메시지 | 새 조각 없음. 비차단 오류가 격리될 때 형 이름이 원래 오류로 바뀐다(예: ConnectionError) | 예 |
| 로그 | 새 로거 `naechaget.floor_refresh` WARNING 1종 | 예 |

## 6. 한계 · 후속
1. **배포 당일 캐러셀 장수**(§1.4) — 추천을 다시 계산할지는 배포 창에서 정한다.
2. **§1.5 의 두 틈** — 재판매 칸 bid_state 조건, 임박 알림. 둘 다 티켓 후보다.
   - 둘 다 지금 데이터에서는 영향이 0 이다.
   - 알림 쪽은 10-09 경 E300 으로 드러날 수 있다(추정).
3. **N3는 그대로다.** 520d 상한선은 재등급 `--apply` 뒤 값이다. 이번 변경과 무관하며, 배포 순서 조건도 그대로다.
4. **C.4-6(재조회 첫 실행 승인)은 여전히 오너 몫이다.** qa 는 N2 수정 뒤에 승인하라고 권고했고, 이번에 N2 가 닫혔다.
5. **REC-7 ⑹ 대조는 app.py md5 fb9d2b8d 판 기준이다.** frontend 의 최종 판과는 다를 수 있다(미검증).

## 7. 확인 · 추정 · 미검증
**확인(재현)**
- §1.1 전후 결과, §1.3 등식, 계산 경로 불변
- §2.3 여섯 상황, finally 10곳 분류
- §3 표와 불일치 0
- 테스트·변이·스위트 수치
- 실행 전후 DB md5 불변, 외부 연결 시도 0

**추정**
- E300 이 10-09 경 임박 알림에 들어온다(판정·가드가 그대로라는 전제).
- 속도 측정은 부하 중에 쟀으므로 '퇴행 없음' 정도로만 읽는다.
- nomarket 문장이 시세 있는 특수차에서 틀릴 수 있다(09-29 에는 0대).

**미검증**
- 운영 DB 의 배포 당일 저장 추천 구성(날마다 다르다)
- frontend 최종 app.py 판과의 ⑹ 대조
- 서버 로그 설정에서 WARNING 이 journald 로 남는지(로거 전파 기본값에 기댄다)

## 8. 파일 · 스크립트
**변경**
- `web/service.py`(md5 d8a5866f)
- 신규 `tests/test_rec1_r3_picks_gate_block.py`(c2f01abd)

**scratch `…/scratchpad/r3/`**
- 하네스: `h3.py`(시각 고정·네트워크 기록)
- N1 재현: `n1_repro.py` · `before_1200.txt` · `b_*.txt` · `a_*.txt` · `after_*.txt`
- 실데이터 등식: `n1_parity_real.py` · `parity_*.txt`
- 조사: `resale_states.py` · `alert_check.py` · `hold_check.py` · `hold_*.txt` · `perf_picks.py`
- 변이: `mutate_r3.py` · `mut_r3.json`
- 스위트: `full_wt.txt` · `full_itree.txt` · `tree_md5_suite_start.txt`
- 트리: `btree`(2회차 판) · `mtree`(변이) · `itree`(격리)