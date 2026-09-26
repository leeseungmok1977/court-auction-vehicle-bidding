# FEAT-2 수정 회차(r2) — qa·디자인 지적 반영 (2026-09-27-31 / frontend-engineer)

- 기준 커밋: `4aa6e47` (작업 트리 **커밋하지 않음** — 커밋·배포·라이브 요청 없음). 서버 파일(`web/app.py`·`web/db.py`·`web/service.py`)은 **손대지 않았다**(mtime 01:00~01:22 < 이 회차 시작 03:00, 확인된 사실).
- 바뀐 파일 2개: `web/templates/vehicles.html` · `tests/test_feat2_year_km_select.py`. `npm run build:css` 실행 → `web/static/app.css` md5 `823a1e8b…` 빌드 전후 동일 = HEAD 와 동일(새 유틸리티 없음, 확인된 사실).
- 측정 조건: 로컬 `127.0.0.1:8982`(금지 포트 9종 회피, 측정 후 종료 — 8765 는 PID 5988 그대로), `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`, DB 는 **r1 과 같은 사본** `feat2.db`(01:47 `mode=ro` + `sqlite3.backup`, 1,418행·공개 1,163건) — r1 캡처와 DB 가 같아 차이는 템플릿뿐. 공개 뷰는 `x-forwarded-for`. Playwright Chromium 148 headless, DPR 1, 높이 900, ko-KR, 비로그인, `networkidle`+300ms. 운영 DB 쓰기·라이브 요청 없음.

## [요약]

디자인 배포 조건 1(미상 문구 자리)을 지시서가 준 방법 그대로 반영했다 — `namespace(parts=[], km_idx=-1)` 에 주행거리 부품 인덱스를 기억하고 `#condSummary` 루프 안 `loop.index0 == _cs.km_idx` 인 부품 뒤에만 mut span 을 찍는다. 렌더 결과 `1,000~2,000만 · 2020년 이후 · 10만km 이하 (주행거리 미상 6건 제외) · 매각기일순 · 필터 초기화` (디자인 보고 목표 문자열과 **한 글자도 다르지 않음**). 부품 수·순서 불변이라 큰글씨 접힌 머리 `— 현대 외 3`·title(미상 없음) 그대로. 6폭 × 6URL + 0건 + 큰글씨 = 41 레코드 전부에서 문구의 앞 형제 = `10만km 이하`, 뒤 형제 = 구분점. 캡처 14장 md5 r1 과 전부 상이·r2 안 중복 0 + `HEAD.txt`. 테스트: FEAT-2 두 파일 134 passed + 1 xfail, 회귀 4파일 208 passed, **전체 1,837 passed · 3 xfailed · 0 failed**(326초). qa 항목 1(쿼리 상한)은 서버 결함이 아니라 비용이라 **반영하지 않았다**(§2 이유).

## 1. 반영 여부 — 지시서 항목별

| # | 지적 | 처리 | 근거 |
|---|---|---|---|
| 3 (디자인 조건 1) | `(주행거리 미상 N건 제외)` 를 주행거리 부품 바로 뒤에 | **반영** | §3 원문 대조 · §4 측정 · §5 캡처 |
| 1 (qa F 쿼리 상한) | `_maker_variants` 가 `_vehicles_where` 호출마다 DISTINCT 실행, maker 페이지 8→12 | **반영하지 않음** — 백엔드 티켓 권고 | §2 |
| 2 (qa 거짓 양성 6건) | 앱 결함 아님, qa 가 자기 술어를 교정 | **해당 없음**(화면 수정 대상 없음) | qa 보고 §1-2 가 이미 `tests/test_feat2_qa_adversarial.py` 에 교정본으로 고정 — 이번 회차 134 passed + 1 xfail 로 그 술어들이 새 템플릿에서도 초록 |
| 비차단 [티켓 갱신] DES-3 본문 넓히기 · [Q1] 폴드 접기 티켓 | **손대지 않음** — `docs/backlog.md` 는 내 범위(템플릿·CSS) 밖 | Steward 가 티켓화. 근거 캡처는 이번에도 나왔다(§5 `large-360-hyundai-collapsed.png` 는 첫 부품 `현대` 라 안 잘림 — DES-3 조건은 첫 부품이 가격대·날짜일 때) |

## 2. 항목 1을 반영하지 않은 이유 (판단 — 서버 결함이 아니라 비용)

지시서 규칙: "서버 파일은 지적이 **서버 결함**일 때만 최소 수정". 이 지적은 결함이 아니다.
1. **정확성 무관·비차단** — qa 판정 원문: "정확성 무관·비차단(1,418행 DISTINCT, ms 단위 — 추정)", "정확성 결함 0건". 축별 COUNT 자체는 지시서 상한(+2)대로다.
2. **qa 스스로 FEAT-2 밖으로 뺐다** — 원문: "고치는 방법은 FEAT-2 밖(요청 단위 캐시 또는 `_vehicles_where` 밖에서 1회 조회해 넘기기) — 별도 티켓 권고, P3".
3. **최소 수정으로 될 일이 아니다** — `_maker_variants` 는 `web/db.py` `_vehicles_where` 안에서 호출되고, 그 조립을 목록 + `count_by_price_band`·`count_by_year_min`·`count_by_km_max` 가 함께 쓴다. 조회를 끌어올리면 시그니처와 세 호출부(`web/service.py`)를 같이 바꿔야 하고, TTL 캐시는 새 maker 표기가 반영되기까지의 지연이라는 **정확성 트레이드오프**를 들여온다 — 화면 담당이 정할 일이 아니다.
4. **표식은 이미 있다** — `test_known_cost_maker_variants_lookup_at_most_twice_per_request` 가 xfail(strict)라 백엔드가 고치면 XPASS 로 드러나고, `…_is_exactly_list_plus_three_facets` 가 현재값 4 를 고정한다. 둘 다 그대로 둔다(고치는 커밋이 함께 지운다).

## 3. 바꾼 것 (앵커 — 줄 번호 없음) 과 요구 원문 대조

| 파일 | 앵커 | 내용 |
|---|---|---|
| `vehicles.html` | `{% set _cs = namespace(parts=[], km_idx=-1) %}` | 네임스페이스에 `km_idx=-1` 추가 |
| `vehicles.html` | `{% if km_max %}{% for o in km_options if o.key == km_max %}{% set _cs.km_idx = _cs.parts|length %}` | 주행거리 `append` **직전**에 `_cs.parts|length` 저장(지시서 방법 그대로). 부품에는 넣지 않는다 |
| `vehicles.html` | `_cs` 블록 주석 `'주행거리 미상 N건 제외' 는 부품이 **아니다**` | "아래 #condSummary 끝에" → "주행거리 부품 바로 뒤에" 로 본문 갱신(규칙 8 — 가리키는 내용이 거짓이 되지 않게) |
| `vehicles.html` | `<p id="condSummary"` 안 `{%- if loop.index0 == _cs.km_idx and km_max and km_unknown_excluded %}` | 루프 **안**, 해당 부품 span 바로 뒤에 같은 mut span(`text-mut whitespace-nowrap`·괄호) — 톤 불변. 루프 뒤의 옛 분기는 삭제. `km_unknown_excluded` 0 이면 여전히 안 그린다(프론트 §6-4 판정 유지) |
| `tests/test_feat2_year_km_select.py` | `test_summary_line_parts_and_collapsed_head` | ⑩ 정확 문자열을 새 순서로 갱신 + **뒤에 부품이 둘(정렬·페이지) 오는 경우**(`&page=2`, 13행이라 2페이지가 실제로 있음)와 주행거리가 마지막 부품인 경우 추가. 접힌 머리 `— 현대 외 3`·title 검사는 그대로 |
| 같은 파일 | docstring ⑧ | "요약 줄 끝" → "주행거리 부품 바로 뒤" |

**요구 원문(디자인 보고 고칠 것 1 목표)**: `1,000~2,000만 · 2020년 이후 · 10만km 이하 (주행거리 미상 6건 제외) · 매각기일순 · 필터 초기화`
**렌더(사본, 360·1440 combo, `#condSummary` textContent)**: `1,000~2,000만 · 2020년 이후 · 10만km 이하 (주행거리 미상 6건 제외) · 매각기일순 · 필터 초기화` — 동일.
**qa D 가 본 최악 사례** `현대 · 2018년 이후 · 10만km 이하 · 매각기일순 · 2/11페이지 (주행거리 미상 11건 제외) · 필터 초기화` → 지금 `현대 · 2018년 이후 · 10만km 이하 (주행거리 미상 11건 제외) · 매각기일순 · 2/11페이지 · 필터 초기화`(`select-360-many.png`·`select-1440-many.png`).
**지시서 검증 항목**: ⑩ 새 순서 갱신 ✓ · 접힌 머리 `— 현대 외 3` 불변 ✓(테스트 + 큰글씨 320·360 실측 `{'text': '— 현대 외 3', 'title': '현대 · 2018년 이후 · 10만km 이하 · 매각기일순', 'clipped': False}`) · 360 combo md5 `92ec5e39…` ≠ `74f2b104…` ✓ · 1440 combo `a978069e…` ≠ `62e749b2…` ✓.

건드리지 않은 것: Jinja 로직·매크로·href·id·필터, 셀렉트 title 문구(그대로 `· 주행거리 미상 N건 제외`), 칩, 검색 저장 스크립트, 서버 3파일.

## 4. 6폭 재측정 (확인된 사실 — `measure_feat2r2.py` 41 레코드)

URL 6종: `unselected` · `year2018` · `km100k-hyundai`(148) · `combo`(123) · `hyundai-combo`(=테스트 ⑩ URL, 128) · `many`(hyundai-combo + `page=2`) + `zero`(360) + 큰글씨 hyundai-combo 320·360 접힘/펼침.

| 폭 | 가로 스크롤 | 뷰포트 밖(설계 외) | 그리드 행 | 빈 셀 | 연식·주행 셀렉트 잘림 | 첫 활성 칩 ✕ ≤ 페이드 | 칩 높이 | 요약 줄 수 (year/km/combo/hyundai/many) | 문구 앞·뒤 형제 |
|---|---|---|---|---|---|---|---|---|---|
| 320 | 없음 ×6 | 0 — 단 `many` 에서 페이지네이션 `‹ 이전`·`다음 ›` 2건(**기존**: 축 없는 `/vehicles?page=2` 에서도 같은 2건, 대조 실측) | [127 127]/[262]×3/[127×42 127×42] | 0 | 없음(215 여유) | 248·250·265 ≤ 275 ✓ | 26 | 1/2/2/2/**3** | `10만km 이하` · `·` |
| 360 | 없음 | 0 | [147 147]/[302]×3/[147 147] | 0 | 없음 | ≤ 315 ✓ | 26 | 1/1/2/2/2 | 같음 |
| 390 | 없음 | 0 | [162 162]/[332]×3/[162 162] | 0 | 없음 | ≤ 345 ✓ | 26 | 1/1/2/2/2 | 같음 |
| 430 | 없음 | 0 | [182 182]/[372]×3/[182 182] | 0 | 없음 | ≤ 385 ✓ | 26 | 1/1/2/2/2 | 같음 |
| 768 | 없음 | 0 | (sm flex) | – | canvas 플래그 `year_min 109 > 108` 은 qa §1-2 ④ 와 같은 반올림 — **Chromium 실측 `scrollWidth == clientWidth`(153·154)** | (페이드 없음) | 26 | 1/1/1/1/1 | 같음 |
| 1440(프레임 420) | 바깥·프레임 없음 | 0·0 | [177 177]/[362]×3/[177 177] | 0 | 없음 | ≤ 375 ✓ | 26 | 1/1/2/2/2 | 같음 |

- 그리드·셀렉트·칩 수치는 r1/qa 표와 **전부 같다**(문구 자리만 바뀌었으니 당연하고, 그것이 확인됐다). 0건 화면 `zero-360.png`: `(0)` 셋 + 빈 결과 카드(하단 794) + 초기화, 미상 문구 없음 — r1 과 같음.
- 큰글씨(hyundai-combo): 320 요약 3줄·360 2줄, 칩 32 균일, 접힌 머리 `— 현대 외 3` **잘림 없음**, 320 밖 요소 3건(헤더 검색 아이콘·페이지네이션)은 FEAT-1/qa 와 같은 기존 3건.
- `many` 320 일반 모드의 페이지네이션 2건은 FEAT-2 무관(대조 URL 재현) — 기존 결함 목록(qa §3-3 은 큰글씨 ≤360 으로 적었는데 **일반 모드 320 도 2페이지 이상이면** 같다). 티켓 후보.

## 5. 캡처 (`screenshots/feat2-r2/`, 14장 + `HEAD.txt` — 기준 커밋 `4aa6e47` + dirty 목록 + 조건 + md5)

| 파일 | md5 | r1 같은 이름 | 내용 |
|---|---|---|---|
| `select-360-combo.png` | `92ec5e39…` | `74f2b104…` **상이** | 지시서 요구 캡처 1 |
| `select-1440-combo.png` | `a978069e…` | `62e749b2…` **상이** | 지시서 요구 캡처 2 |
| `select-320/390/430/768-combo.png` | `45879300…`/`77371779…`/`43c7e868…`/`739adb23…` | 390·768 상이 | 6폭 combo |
| `select-360-many.png` / `-1440-` | `9e93c7aa…` / `c21c3b3a…` | (신규) | 문구 뒤에 정렬·페이지 부품 둘 |
| `select-360-km100k-hyundai.png` / `-1440-` | `19d950f9…` / `a36d9901…` | 상이 | 부품 둘 — r1 에서 "우연히 붙은" 경우, 지금은 규칙으로 붙음 |
| `large-360-hyundai-collapsed.png` / `-expanded` | `c8ee6f4a…` / `d2aa977c…` | (신규) | 접힌 머리 `— 현대 외 3` |
| `unselected-320.png` / `zero-360.png` | `048923fa…` / `baf6593f…` | 상이 | 대조군(문구 없는 화면) |

r2 안 md5 중복 0. **눈으로 연 것**(Read): `select-360-combo`·`select-1440-combo`·`select-360-many`·`large-360-hyundai-collapsed`·`select-320-combo`·`select-768-combo` — 파일명·내용 일치, 여섯 장 모두 괄호가 `10만km 이하` 뒤·`매각기일순` 앞.

**md5 상이의 뜻을 정직하게**: 문구 없는 대조군 `unselected-320` 도 r1 과 md5 가 다르다(26225→26241 B). 픽셀 diff(PIL) 결과 차이는 **x29–32·y255–325 의 20px** — 셀렉트 왼쪽 테두리 안티앨리어싱 정도이고 문구 영역이 아니다(원인은 **추정**: 같은 템플릿을 두 번 찍어도 이 슬리버는 달라졌다 — 03:18 첫 실행 26225 B, 03:20 재실행 26241 B). 반대로 `select-360-combo` 의 차이 1,143px 중 **1,129px 이 요약 줄 띠(y480–540)** 에 있고 나머지 14px 은 같은 슬리버다. 즉 md5 상이는 필요조건일 뿐이고, 자리가 바뀌었다는 증거는 §4 의 형제 측정과 눈으로 본 캡처·픽셀 diff 의 위치다.

## 6. 테스트 (확인된 사실 — pytest 출력)

| 명령(`NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1 python -m pytest … -q -p no:cacheprovider`) | 결과 |
|---|---|
| `tests/test_feat2_year_km_select.py tests/test_feat2_qa_adversarial.py` | **134 passed, 1 xfailed**(30 + 104 + xfail 1), 38.7초 — qa 의 교정된 술어 전부가 새 템플릿에서 초록 |
| `tests/test_feat1_price_select.py tests/test_feat2_year_km_filter.py tests/test_ux2_ux5_nav_state.py tests/test_ux_round3.py` | **208 passed**(21 + 131 + 33 + 23), 62.0초 |
| 전체 스위트 | **1,837 passed, 3 xfailed, 0 failed**, 326.3초(5:26) — qa 보고와 같은 수(이번 회차는 테스트 함수를 늘리지 않고 ⑩ 안의 단언만 셋 늘렸다). 측정 서버·Playwright 와 동시에 돌렸다 |

## 7. 판단 요청·남긴 것

1. **(디자인 판정 요청) 320·360 에서 문구가 줄 머리로 내려간다** — `select-360-combo.png`: 1줄 `1,000~2,000만 · 2020년 이후 · 10만km 이하`, 2줄 `(주행거리 미상 6건 제외) · 매각기일순 · 필터 초기화`. DOM·읽는 순서는 주행거리 바로 뒤이고 문구는 nowrap 이라 낱말 안에서 갈리지 않지만, 좁은 폭에서 괄호가 앞 낱말과 **다른 줄**에 놓인다. 대안은 부품+문구를 한 nowrap 덩어리로 묶는 것 — 단 360 combo 가 3줄이 된다(추정: 2줄째 ≈280px 는 들어가고 `필터 초기화` 가 3줄로). 지시서 방법(부품 뒤 별도 span)을 그대로 따랐고 바꾸지 않았다.
2. 항목 1(`_maker_variants` 4회) — 백엔드 티켓으로(§2).
3. `docs/backlog.md` 갱신(DES-3 범위·Q1 폴드 접기·320 일반 모드 2페이지 페이지네이션 넘침) — 범위 밖, Steward 티켓화.
4. 라이브·실기기 미측정(사본 기준). 앵커 점프·고정 요소는 만들거나 옮기지 않아 해당 없음.

**확인된 사실**: §3 diff·원문 대조, §4 41 레코드 수치·대조 URL·`scrollWidth`, §5 md5·픽셀 diff 위치, §6 테스트 수, app.css md5 동일, 서버 파일 mtime, 8765 무접촉·8982 종료. **추정**: 대조군 슬리버의 원인, §7-1 대안의 줄 수.
