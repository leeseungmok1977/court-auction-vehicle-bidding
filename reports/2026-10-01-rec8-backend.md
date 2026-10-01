---
order: 2026-10-01-03
from: backend-engineer
ticket: REC-8
result: done
verified: 재현
handoff: []
---

# REC-8·REC-9 서버 쪽, 유망 물건 재판매 칸, /privacy 시행일 (지시서 2026-10-01-03)

> Steward 옮김(2026-10-01): 담당은 하네스 규칙상 파일을 쓰지 못해 본문을 인계 메시지로 보냈다. 아래는 그 본문의
> [요약]·§4 명세·§5 결정 요청·§6 을 **문장 그대로** 옮긴 것이다. §1~§3(변경 상세·전후 수·테스트)은 요점만 적었다.

> **기준**: HEAD 2bf32b3 위의 작업 트리. 커밋·배포·ssh·외부 요청 0. 운영 8765·data/ 무접촉. 판정 기준 값 그대로(config.yaml md5 5411eb7a).
> **바꾼 파일**: web/app.py(deb9ea97) · web/service.py(74de9b9b) · web/db.py(577f595e) · tests/test_promising_picks.py 픽스처 1줄(R1_1 upper_bid=12_000_000) · 새 테스트 4파일(test_rec8_judgment_filter 31 · test_rec8_run_status 10 · test_rec9_no_estimate 28 · test_rec8_promising_resale 5). 템플릿은 한 줄도 고치지 않았다.

## [요약]

**REC-8 ⑴ — 판정 필터 = 칸 (확인)**
- 이제 `/vehicles?judgment=입찰 검토 가능` 은 `?bucket=review` 와 같은 목록이다.
- 6개 조합(사본 2벌 × 09-29 09:00·12:00·10-09 09:00)을 모두 대조했다. 같은 것: id·순서(정렬 5종)·총수·페이지·가격대/연식/주행거리 건수·저장 검색 건수.
- 총수 전: 4/3 · 4/2 · 1/0 · 5/3 · 5/2 · 2/0 → 후: 3/3 · 2/2 · 0/0 · 3/3 · 2/2 · 0/0. 빠진 것은 가드(E300·520d)와 기일 경과(체로키)뿐이다.

**REC-8 ⑵ — /run/status (확인)**
- 응답에서 ok·wait·hold 를 뺐다(공개·관리자 모두). 공개 응답에서는 total 도 뺐다.
- upcoming 은 홈과 같은 정의로 센다: 491 → 417, 홈도 417.
- 폴링 비용은 줄었다(중앙값). 실행 중 38~44 → 24~27ms, 유휴 19~22 → 6.5~7.4ms.
- 서버만 먼저 배포돼도 KPI 덮어쓰기가 멈춘다. base.html 의 `setTxt` 가 null 이면 쓰지 않기 때문이다.

**REC-9 — 신호 하나 (확인)**
- 신호 이름은 `no_estimate` 이고 세 곳에 실린다: bid_state 결과(bidst), plain_verdict 결과(verdict), 관심 화면 행.
- 값은 한 함수 `service.estimate_withheld` 가 정한다. 판정 문장("…제공하지 않습니다")의 조건도 이 함수다.
- 09-29 사본의 침수 등급 9대: 차단 6대 → 참, 매각 종료 3대 → 거짓. 밴드가 그려지던 물건은 34408 한 대다.

**추가 지시 — 유망 물건 재판매 칸 (확인)**
- 캐러셀과 같은 함수 `resale_pick_ok` 를 쓴다. 520d 재조회 값 픽스처로 재현했다: 전에는 '되팔아도 남음'으로 섰고, 후에는 목록에서 빠진다.
- ⚠ '실사용 갈래로 다시 심사'는 두 곳(유망·캐러셀) 모두 실제로는 아무것도 하지 않는다. `personal_use_tier` 는 저장 판정이 '입찰 검토 가능'이면 None 을 돌려준다. 그래서 배지가 바뀌지 않고 물건이 빠진다. 캐러셀도 eefc578 부터 같다. 결정이 필요하다(§5-1).

**/privacy** — 시행일을 2026-09-11 → 2026-10-01 로 올렸다.

**테스트** — 새 테스트 74개(4파일). 편집 전 코드에서 66개 빨강, 통과 8개는 전제·불변 확인용이다. 변이 18종 중 17종 KILLED, 생존 1종은 등가다. 전체 스위트 **2,705 passed · 5 xfailed · 0 failed**(656초). 전역 네트워크 가드 켜고 한 번 더: 2,705 passed(828초), 외부 연결 시도 0.

**스키마** — DB·config 변경은 없다. 응답·컨텍스트 모양은 바뀌었다 → §4 명세.

## 1~3 요점 (Steward 요약)
- `/vehicles`: 칸으로 읽는 판정 값이면 SQL 에 저장 문자열을 넘기지 않고 파이썬에서 칸으로 거른다(`JUDGMENT_FILTER_BUCKETS = {"입찰 검토 가능": "review"}` · `judgment_filter_bucket()` · `in_judgment_filter()`). `/api/vehicles/count` 도 같은 칸 필터. 다른 판정 값은 그대로 저장 문자열.
- `/run/status`: upcoming 은 새 `db.count_vehicles(upcoming_days=30, hide_incomplete=True)`. `counts_by_judgment` 호출 제거(웹에서 0곳), 홈 컨텍스트의 죽은 `counts` 제거.
- REC-9: `flood_hold(v)` = 등급 flood 또는 저장 판정 '입찰 보류'. `estimate_withheld(v, st)` = `st.state == "blocked" and flood_hold(v)`. plain_verdict 침수 문장 조건이 넓어졌다(키워드로만 '입찰 보류'가 된 물건도 같은 문장 — 09-29 사본 0대).
- 유망 물건: `resale_pick_ok(v, st)` = 저장 판정 '입찰 검토 가능' ∧ bid_state state == 'resale'. `_daily_pick_gate`·`promising_rows` 가 같은 함수. eefc578 주석("실사용 칸으로 다시 심사")을 사실대로 고쳤다.
- 비용: `/vehicles?judgment=…` 는 느려졌다(65~72 → 232~242ms — `?bucket=review` 와 같은 질의라서). 진입점을 bucket=review 로 바꾸면 더 빠른 경로를 탄다.

## 4. 명세 — frontend 반영

### 4.1 /run/status

| 요청 | 전 | 후 |
|---|---|---|
| 공개·유휴 | {running:false} | 같음 |
| 공개·실행 중 | running·run·total·upcoming·pending·ok·wait·hold | **running·run·upcoming·pending** |
| 관리자(루프백) | 같은 8키 | running·run·upcoming·pending·total |

- `upcoming` 은 이제 홈 `lifecycle.upcoming30` 과 같은 정의다. `pending` 은 그대로다.
- **base.html 에서 할 일**: 폴링의 `setTxt('kpi-ok', fmt(d.ok)); setTxt('kpi-wait', fmt(d.wait));` 를 지운다(키가 없어져 죽은 줄). kpi-upcoming·kpi-pending 덮어쓰기는 같은 정의라 남겨도 되고 지워도 된다. 실행이 끝날 때의 새로고침은 그대로 필요하다.
- ⚠ `setTxt` 의 `v!=null` 가드와 `fmt` 는 유지해 달라. 서버만 먼저 나가도 덮어쓰기가 멈추는 근거이고, 테스트가 고정한다.

### 4.2 홈 컨텍스트
- `counts` 를 삭제했다(안 쓰던 키). 판정 수가 필요하면 `lifecycle` 을 쓴다.

### 4.3 `/vehicles?judgment=입찰 검토 가능` · count API
- 결과·총수·페이지·셀렉트 건수가 `?bucket=review` 와 같다. 컨텍스트 모양은 그대로다: `judgment` = '입찰 검토 가능', `bucket` = ''.
- ⚠ 이름표 문제: 조건 요약 줄과 드롭다운은 여전히 '입찰 검토 가능'이라고 쓴다(jshort 는 이 값을 바꾸지 않는다). 같은 집합이 칩에서는 '지금 입찰 추천', 여기서는 '입찰 검토 가능'으로 불린다. 이름을 맞출지는 frontend·Steward 몫이다.
- 진입점 6곳을 `bucket=review` 로 바꾸는 권고는 그대로다: dashboard '더보기 →'(캐러셀 머리)·'✅ 검토 가능' 칩 / landing '지금 검토 가능한 물건 →'·'유망 물건 보기' / vehicles '🎯 검토 추천 ✕'·'되팔이 기준 보기'.
- 다른 판정 값은 그대로 저장 문자열이다.

### 4.4 REC-9 신호

| 키 | 위치 | 모양 |
|---|---|---|
| `bidst.no_estimate` | 목록 카드 `v.bidst`, 상세·리포트 `bidst` | bool, 항상 있음 |
| `verdict.no_estimate` | 상세·리포트 판정 상자 | 침수 문장일 때만 True(그 밖엔 키 없음) |
| `v.no_estimate` | 관심 화면 행 | bool, 항상 있음(가드 행에만 bidst 가 있어서 따로 둠) |

- 셋 다 `service.estimate_withheld` 값이다. 값은 None 이 아니다. `expected`·`expected_win`·`report.exp/lo/hi`·`allin` 이 모두 온다. 가리는 것은 템플릿이다.
- 키워드로만 보류된 물건은 `bidst.max_bid` 가 있다(등급 flood 는 None). 그래서 상한선도 `no_estimate` 로 가려야 한다.

**`no_estimate` 가 참일 때 가릴 자리 (앵커 문자열)**

detail.html
1. 가격 목록의 '입찰 상한선' 행 `{% if bidst and bidst.max_bid %}`
2. `{% if allin %}` '낙찰 시 최소 예상비용 · 예상낙찰가 기준'
3. 히어로 `{% if v.median_price is not none and expected and expected.price %}`('AI 낙찰 예측 분석') — 대표 숫자(상한선 또는 'AI 예상낙찰가'), 게이지와 범례 '예상', '산정 기준' 줄
4. '추천 입찰 전략' — 지금 `v.accident_grade == 'flood'` 로 금액을 숨긴다. 조건을 `bidst.no_estimate` 로 바꿔 달라. 키워드로만 보류된 물건은 지금 '손익분기를 넘어'라는 다른 이유가 나온다.
5. '소매 시장 대비 차익' `{% if expected and expected.price and eff_median and eff_median > expected.price and not _closed %}` — 34408 이 여기 그려진다.
6. '입찰가 산정 근거' `{% if expected and expected.price and expected.basis and expected.basis.kind == 'min_premium' %}`

report.html
1. §01 `.vgrid` 첫 칸 — `{% if max_bid and _danger %}` 갈래와 `{% else %}` 갈래('예상낙찰가' `v-band num` + '중심값'). 34408 은 else 갈래로 가서 1,230~1,460만이 가장 큰 글자로 나온다. REC-9 원문 장면이다.
2. §01 `ul.vpts` '{% if _st == 'blocked' %}이미 입찰 상한선을 넘습니다' — 침수도 state 가 blocked 라 이 문장이 나온다. 상한선이 없는데 넘는다고 하니 거짓이다.
3. §01 요점 '소매 시세중앙값 … 대비 이 물건의 예상낙찰가는 약 N%'
4. §01 요점 '준비할 현금은 총 …'(`report.allin_ref`)
5. 스펙트럼 막대 `{% set gmax = [med, floor, upper, max_bid or 0, report.hi or exp]|max %}`
6. §06 총 취득원가(`abasis_ko`·`abid`)
7. §07 수익 시뮬레이션(`report.sim`)
8. §08 민감도(`report.sens`)
9. §10 산출 로직의 '예상낙찰가 분위수 밴드'·산정식
10. (관리자 전용) `dist` 히스토그램의 예상 표식
- 참고: §01 육각형 '가격 메리트'는 최저가÷시세라 예상가가 아니다. 34408 에서는 높게 나온다(판단 필요, 가릴 목록 밖).

vehicles.html
1. 카드의 'AI 예상낙찰가' 숫자 `v.expected_win`
2. 카드 '입찰 상한' 줄 `{% if not closed and v.bidst and (v.bidst.max_bid or v.bidst.exp_pinned) %}`
3. 표(lg+)의 '예상낙찰가' 열(`exp_far` 칸)과 미니 게이지

watchlist.html — 표·카드 모두: '예상낙찰가'(`v.expected_win`), '여유'(`margin_room` = 예상 − 최저)

가릴 것 없는 화면: dashboard(캐러셀·유망 물건·임박 알림에는 침수차가 구조상 서지 않는다 — 테스트 고정), calendar·courts·accuracy·landing(개별 예상가 없음).

정렬: `sort=expected`, 관심 화면 '예상낙찰가 높은순'·'여유 큰 순'은 가린 값으로도 정렬한다. 서버는 그대로 뒀다(후속 선택).

### 4.5 유망 물건 `pick_kind`
- 모양은 그대로다. 'resale' 의 뜻만 좁아졌다(판정이 되팔이일 때만). 템플릿 변경은 필요 없다.

### 4.6 스키마 요약
- DB·config: 없음. 새 조회 함수 `db.count_vehicles` 만 추가.
- /run/status: 키 3개 삭제, 공개 total 삭제, upcoming 정의 변경. 홈 컨텍스트: `counts` 삭제.
- bid_state·plain_verdict·관심 화면 행: `no_estimate` 추가. /privacy: updated 값. 모두 하위호환이다.

## 5. 결정 요청 · 한계 · 후속

1. **[Steward 결정]** 판정이 '지금 사면 이득'인 저장 '입찰 검토 가능' 물건(520d 류)을 어떻게 할지. 선택지 A — 유망 물건·캐러셀에서 **뺀다**(현행). 선택지 B — **'지금 사면 이득' 배지로 남긴다**(`personal_use_tier` 의 제외 줄을 배지 심사에서만 풀어야 한다, 완화 방향, 칸 연결이 어긋난다). 권고: 지금은 A 로 두고, REC-2(칸 정의)에서 함께 정한다.
   → **Steward 결정(2026-10-01): A.** 틀린 배지보다 빠지는 편이 안전하다. REC-2 에서 칸 정의와 함께 다시 본다.
2. 판정 드롭다운 나머지 값의 뜻과 '입찰 검토 가능' 이름표는 Steward·frontend 몫이다.
3. REC-8 ⑶(알림 '전체 N건 →')은 템플릿이라 손대지 않았다.
4. 곁가지(확인, 안 고침): `/api/vehicles/count` 가 `promising` 파라미터를 받지 않는다. 지금은 그 파라미터로 가는 링크가 0이다.
5. 곁가지(확인, 안 고침): 홈 컨텍스트 `upcoming`(db.upcoming_count, 숨김 포함)도 어느 템플릿도 읽지 않는 죽은 값이다.
6. 배포: 서버만 먼저 나가도 안전하다. REC-8·9 가 화면에서 닫히려면 frontend(진입점·가리기)와 같이 나가야 한다.

## 6. 확인 · 추정 · 미검증
- **확인(재현)**: 전후 수 전부(6조합), 비용 수치(조건 명시), 침수 9대의 신호 값, 520d 픽스처의 전후, 반증·변이·스위트 두 판, 외부 연결 시도 0, 사본 md5 불변.
- **추정**: 비용 절대값, 10-09 반사실의 발현.
- **미검증**: 운영 DB 의 오늘 구성(ssh 금지 — 라이브 520d·봉고·E300 의 유망 물건 표시는 Steward 인용, 520d 만 같은 값으로 재현). 수집 창에서의 실제 폴링 부하. 실제 폰·TWA. frontend 최종판과의 조합.
- scratch: `…\scratchpad\rec8\` (probe8·summ8·perf8·mut8·full_wt·h8).
