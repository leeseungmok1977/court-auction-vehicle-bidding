# UX 묶음 3차 — 디자인 지적 3 + qa 회귀 1 + 기존 틈 3 (frontend 보고, 지시서 2026-09-26-26)

기준 커밋 `576de11` + 작업 트리 dirty(1·2차 backend/frontend 변경 + Steward `docs/backlog.md`, 커밋 없이 그 위에서 작업). 커밋·배포·라이브 요청 없음. `web/app.py`·`web/db.py`·`web/service.py` 무접촉(`git diff --stat` 이 2차와 같은 줄 수). 운영 DB 는 `mode=ro` 로 열어 backup 사본만(원본 mtime `2026-09-23 15:27` 그대로). 8765 무접촉, 금지 포트 9개 미사용(측정 서버 52062·테스트는 OS 가 비운 포트). `npm run build:css` 1회(새 유틸리티 `sm:min-w-[12rem]` 1개 — `app.css` 규칙 HEAD 810 → 818 = 2차 7 + 이번 1, 추가만).

## [요약]
- **9항목 전부 반영.** 요약 줄 날짜 `2026-09-01 매각`(칩과 동일 문자열) · 구분 줄 `지난 기일 N건 — 낙찰은 결과 참고 · 유찰은 다음 기일 대기`(`split_note` 한 변수, 카드·표) · 큰글씨 접힌 머리 `검색 · 필터 — 현대 외 3`(부품 단위) · [적용] is-dirty 되돌림(폼 직렬화 비교) · 상세 제목 열 `sm:min-w-[12rem]`(공개 뷰 640/700/768 제목 열 0/28/96 → **192**, h1 64 → **32**, 액션 줄 넘침 0) · `all` hidden(`request.query_params` — **`all` 은 라우트 컨텍스트에 없었다**, app.py 무접촉) · 검색 저장 라벨 date·court(칩 규칙)·result·bucket·usepick·picks·promising · `frame.html` `\` 거부 + 출처 대조(두 곳) · qa strict xfail 3건 → 정상 테스트(단정 원문 그대로, **3건 모두 passed**).
- **판단 1건(지시서 "우선 검토"와 다른 곳)**: 검색 저장 라벨의 **`_cs.parts` 전면 주입은 하지 않았다** — FEAT-1 ⑤(`tests/test_feat1_price_select.py::test_save_search_script_gets_label_map_from_server`)가 이 함수의 JS 원천(`p.get('price')`·`parts.push('최저가 '+PB[pb])`)과 "저장 라벨은 `최저가 ` 접두" 판정을 고정하고 있어, 전면 주입은 FEAT-1 판정 변경을 수반한다. 사전형(버킷·실사용 갈래)만 Jinja 주입(`bucket_labels`·`use_tier_labels|tojson` — 칩·요약 줄과 같은 원천), 공식형(date·court·result·picks·promising)은 칩과 같은 식으로 최소 추가. 런타임(실제 클릭 → localStorage 라벨) 3케이스 Playwright 로 단정.
- **잔여 1건(신규 발견, 비차단·판정 요청)**: 큰글씨 접힌 머리에서 **첫 부품 자체가 긴 조합**(날짜·가격대가 첫 부품 = 제조사·판정 없이 그 필터만 건 경우)은 360 에서 숫자 온전(`— 2026-09-01 매...`·`— 1,000~2,000만...`, `외 N` 이 말줄임 뒤로 숨음) 이지만 **320 큰글씨에서는 숫자 안이 잘린다**(`— 2026-09...`·`— 1,000~2,...`, span 111px vs 필요 183/166). 지시서 캡처 기준(360)은 충족, critic 처방(첫 부품 + 외 N) 그대로의 한계라 새 어휘를 만들지 않고 §6 에 선택지를 적었다.
- 테스트: 신규 `tests/test_ux_round3.py` **23**(템플릿 7 + Playwright 16) 초록. 지시서 7파일 **219 passed, 2 xfailed**(2차 212 + qa 7 = 219; xfail 5 → 2 = FEAT-1 qa 기존 2건만). 전체 스위트 §5.

## 1. 항목별 바꾼 것 (파일 · 앵커 — 줄 번호 없음)

| # | 항목 | 파일 · 앵커 | 바꾼 것 | 근거·확인 |
|---|---|---|---|---|
| 1 | 요약 줄 날짜 | `vehicles.html` `{% if date %}{% set _ = _cs.parts.append(` | `((date[5:7]\|int) ~ '/' ~ …)` 식 → `date ~ ' 매각'`. 위에 주석(왜 ISO 인지). 큰글씨 접힌 머리도 같은 부품 | 렌더 `2026-09-01 매각 · 매각기일순 · 필터 초기화` — 칩 `2026-09-01 매각 ✕` 와 같은 문자열(테스트가 두 자리를 대조). 320·360·390·430 전부 **1줄**(20px), 768·1440 1줄(링크 없음). `date[5:7]` 템플릿에서 사라짐 |
| 2 | 구분 줄 문구 | `vehicles.html` `{% set split_note = '낙찰은 결과 참고 · 유찰은 다음 기일 대기' %}`(has_filter 바로 아래) · 표 `<tr data-sale-split` · 카드 `<div data-sale-split` | 두 자리의 `건 — 낙찰 결과·다음 기일 대기 참고` → `건 — {{ split_note }}`(한 변수). 건수 쉼표(`'{:,}'.format`) 유지 | 사본 `?sort=sale_date&page=13`(오늘 2026-09-27 에도 13) 카드 `지난 기일 1,019건 — 낙찰은 결과 참고 · 유찰은 다음 기일 대기` 높이 33 · 표(1440) 같은 문구. ⚠ 320 에서는 문구가 길어져 **2줄**(`…유찰은 다음 / 기일 대기`, keep-all 이라 낱말 안 절단 없음) — 캡처 `after-320-date-summary.png` |
| 3 | 큰글씨 접힌 머리 | `vehicles.html` `#listFilter > summary` 안 `<span class="min-w-0 truncate … title="{{ cond_summary }}">` | `— {{ cond_summary }}` → `— {{ _cs.parts[0] }}{% if _cs.parts\|length > 1 %} 외 {{ _cs.parts\|length - 1 }}{% endif %}`. `title` 은 전문 그대로. `truncate` 는 첫 부품이 아주 길 때의 안전망으로만 남김. 두 줄로 풀지 않음(높이 30 유지) | 360 큰글씨 combo `검색 · 필터 — 현대 외 3`(span 86px, 넘침 없음, `…` 없음) — 캡처 `after-360-large-combo.png`. 첫 부품이 긴 조합의 한계는 §6-1 |
| 4 | [적용] is-dirty 되돌림 | `vehicles.html` 하단 IIFE `var f=document.querySelector('#listFilter form')` | `ser()` = `new URLSearchParams(new FormData(f)).toString()`, 로드 시 `base=ser()`, `change`/`input` → `sync()` = `mark(ser()!==base)`. `pageshow` → `mark(false)` 유지 | Playwright: 제조사 현대→기아 채움 → 현대로 되돌림 **해제** · 검색어 입력/지움 · 정렬 변경 채움(`test_apply_dirty_reverts_when_form_returns_to_loaded_values`) |
| 5 | 상세 헤더 제목 열 | `detail.html` `<div class="min-w-0 flex-1 sm:min-w-[12rem]">`(주석 4줄 추가) · 액션 줄 주석(`sm:shrink-0 을 뺐다(2026-09-26)`) 본문 갱신 | 제목 열 최소 폭 12rem(192px, sm 이상). 액션 줄은 그만큼 줄어 flex-wrap 으로 접힘. 주석의 거짓 문장("768 이상 렌더 무변화")을 사실로 고침 | qa D-1 회귀 기준표 재측정 §3-①: 공개 뷰 640/700/768 제목 열 **192**(HEAD 36/96/164), h1 **32**(1줄), 법원·사건 줄 **40**(2줄), 액션 줄 2줄(92) 넘침 0, 문서·`#appscroll` 가로 스크롤 0. 관리자 뷰(6버튼) 동일. 1440 공개 448/관리자 324 — 예전대로 남는 폭 |
| 6 | `all` hidden | `vehicles.html` `{% if picks %}<input type="hidden" name="picks"` 아래 | `{% set all = request.query_params.get('all', '') %}` + `{% if all %}<input type="hidden" name="all" value="{{ all }}">{% endif %}`(주석 3줄) | ★ **확인된 사실**: `vehicles()` 는 `_filters["all"]` 을 만들지만 `TemplateResponse` 컨텍스트에 `all` 을 **넘기지 않는다**(qs 안에만). `app.py` 수정 금지라 `request` 로 읽음. 값은 원값(`_qs` 와 동일 규칙 — 서버는 `all == "1"` 일 때만 숨김 해제, `all=0` 을 `1` 로 승격하지 않음). 테스트: 완전 1 + 불완전 1 → `all=1&maker=현대` 폼 파싱·GET 재현 → 총수 2 유지, 없으면 hidden 없음, `all=0` → `value="0"`, `name="all"` 1개 |
| 7 | 검색 저장 라벨 | `vehicles.html` `function ncSaveSearch()` — `if(p.get('cond')==='damaged')` 아래 · `if(p.get('court'))` | `var BL={{ bucket_labels\|tojson }}, UT={{ use_tier_labels\|tojson }};` + date `p.get('date')+' 매각'` · result `'결과='+…` · bucket `BL[…]\|\|…` · usepick `'실사용 추천'` + (now/cheap 면 ` · ` + `UT[…]`) · picks `'유망 물건'` · promising `'검토 추천'`. court `'법원 지정'` → 칩 규칙(`,` 있으면 `법원 N곳`, 아니면 `지방법원→지법`) | 런타임 3케이스(`date=…` → `2026-09-01 매각` / `court=수원지방법원` → `수원지법` / 6키 조합 → `법원 2곳 · 결과=유찰 · 유찰 대기 · 실사용 추천 · 지금 사면 이득 · 유망 물건 · 검토 추천`), qs 에 `page`·`all` 없음. 기존 부품(q·maker·price·segment·judgment·upcoming·cond)은 손대지 않음(FEAT-1 ⑤ 고정). 전면 주입을 안 한 이유는 [요약] |
| 8 | `frame.html` 가드 | `if (!p.startsWith("/")` · `addEventListener("load"` | 초기: `\|\| p.indexOf("\\") !== -1` + `new URL(p, location.origin).origin !== location.origin → "/"`(try/catch 도 `/`). load: `l.origin !== location.origin → return` + `np.indexOf("\\") !== -1 → return`. `document.getElementById("f").src = p;`·`np.startsWith("//")`·`history.replaceState` 앵커 유지 | Playwright 1440: `#/\evil.example/x`·`#/\\evil.example`·`#//evil.example/x`·`#http://evil.example/`·`#/vehicles\@evil.example` → iframe **`/`**, 127.0.0.1 밖 요청 **0**. 정상 `#/vehicles?maker=…&sort=sale_date` → iframe `/vehicles`, 바깥 해시 갱신 그대로 |
| 9 | qa strict xfail 3건 | `tests/test_ux_batch_qa_adversarial.py` `test_form_keeps_all_param_on_apply`·`test_saved_search_label_reads_date`·`test_frame_hash_guard_rejects_backslash_or_checks_origin` | `@pytest.mark.xfail(strict=True, …)` 세 줄 제거, 각 함수에 "3차에서 고침" 독스트링 1줄, 모듈 독스트링 ④ 갱신. **단정 본문 무변경** | 3건 **passed**(XPASS 아님 — 표식을 뗐으므로 strict 빨간불 없음). 파일 7 passed |

이 회차가 바꾼 **기존 테스트 기대값**(사양이 바뀐 곳만, `tests/test_ux2_ux5_nav_state.py` 4곳): 날짜 부품 `9/1 매각` → `2026-09-01 매각` · 접힌 머리 "같은 문자열" → `— 현대 외 3` + `title` 전문(템플릿·Playwright b6 두 곳) · 구분 줄 문구. 지운 테스트 0.

## 2. 판단 항목
| 항목 | 판단 | 근거 |
|---|---|---|
| 제목 열 처방 | **`sm:min-w-[12rem]`**(후보 ①) | 후보 ②(sm~md 에서 액션 줄을 제목 아래 줄로 = 헤더 `flex-wrap` + `basis-full lg:basis-auto`)는 lg(1024) 사이드바 288px 때문에 1024~1150 에서도 다시 접혀 데스크톱 레이아웃이 바뀐다. ①은 폭이 넉넉하면 예전 렌더 그대로(1440 공개 448·관리자 324 = 남는 폭), 좁으면 제목이 먼저 192 를 갖는다. 12rem 은 HEAD 768 의 164 보다 크고 `기아 카니발`(text-2xl 굵게 ≈130px)이 한 줄. 긴 이름(예 `현대 쏘나타(SONATA)`)은 192 안에서 두 줄 — HEAD 는 그 폭에서 0~96 이라 더 나쁨 |
| `all` 값 | 원값 `{{ all }}`(지시서 예시 `value="1"` 대신) | 페이지네이션 `_qs` 가 원값을 싣는 것과 같은 규칙. `all=0` 진입(무효값 → 숨김 유지)을 [적용]이 `all=1`(숨김 해제)로 바꾸면 모수가 바뀐다 — 지시서가 고치려는 바로 그 사고. qa 단정 정규식(`{% if all %}<input type="hidden" name="all"`)은 그대로 만족 |
| 저장 라벨 원천 | 부분 주입(사전만) | [요약] 2번째 항목. 전면 주입은 FEAT-1 ⑤ 두 단정(`p.get('price')`·`'최저가 '+PB[pb]`)과 "저장 라벨엔 축 접두" 판정을 뒤집어야 해 이번 회차 범위 밖 — Steward 판정 항목으로 §6-2 |
| 구분 줄 한 원천 | Jinja 변수 `split_note` | 매크로보다 가볍고 두 자리(표·카드)가 같은 문자열임을 테스트가 `count("건 — {{ split_note }}") == 2` 로 고정 |
| pageshow | `mark(false)` 유지, base 재설정 안 함 | 지시서 "pageshow 처리 유지". bfcache 복귀 후 바꾼 셀렉트를 또 바꾸면 로드 시 base 와 비교되므로 "폼 ≠ URL" 이 정직하게 채움으로 남는다 |

## 3. 측정 (조건 → §7)

### ① 상세 헤더 `/vehicle/2025타경57868_1`(감정평가서·시세 있음) — qa D-1 표 재측정
| 폭 | 뷰 | 제목 열 HEAD(qa) → 2차 → **3차** | h1 HEAD → 2차 → **3차** | 법원·사건 줄 HEAD → 2차 → **3차** | 액션 줄 폭·높이 3차 | 넘침(줄·문서·appscroll) |
|---|---|---|---|---|---|---|
| 640 | 공개 | 36.4 → 0 → **192** | 64 → 64 → **32** | 160 → 480 → **40** | 400 · 92(2줄) | 0·0·0 |
| 700 | 공개 | 96.4 → 28 → **192** | 64 → 64 → **32** | 80 → 240 → **40** | 460 · 92 | 0·0·0 |
| 768 | 공개 | 164.4 → 96 → **192** | 32 → 64 → **32** | 40 → 80 → **40** | 528 · 92 | 0·0·0 |
| 1440 | 공개 | — → — → 448 | 32 | 20 | 624 · 42(1줄) | 0·0·0 |
| 640/700/768 | 관리자(6버튼, `다시 분석` 있음) | **192** | **32** | **40** | 400/460/528 · 92 | 0·0·0 |
| 1440 | 관리자 | 324.1 | 32 | 20 | 747.9 · 42 | 0·0·0 |
| 320/360/390/430 | 공개·관리자 | 288/328/358/398(세로 쌓임, sm 미만 무변화) | 32 | 20 | 142/142/92/92 | 0·0·0 |
공개 뷰 = `X-Forwarded-For: 203.0.113.9`(`다시 분석` 부재 확인) · 관리자 = loopback.

### ② 목록 2 URL × 6폭(공개 뷰)
| URL | 항목 | 320 | 360 | 390 | 430 | 768 | 1440 |
|---|---|---|---|---|---|---|---|
| date(`?date=2026-09-01&sort=sale_date`, 59건) | 가로 스크롤(문서·appscroll) | 0 | 0 | 0 | 0 | 0 | 0 |
| | 활성 칩 높이 | 26 | 26 | 26 | 26 | 26 | 26 |
| | 첫 활성 칩 pill 우변 / 페이드 | 276.5 / 275 (1.5px, 2차와 동일 — ✕ 글리프는 안) | 276.5 / 315 | 276.5 / 345 | 276.5 / 385 | — | — |
| | 요약 줄 | `2026-09-01 매각 · 매각기일순 · 필터 초기화` **1줄** | 1줄 | 1줄 | 1줄 | 1줄(링크 없음) | 1줄 |
| combo(`?maker=현대&price=1000-2000&sort=sale_date&page=2`, 146건) | 가로 스크롤 | 0 | 0 | 0 | 0 | 0 | 0 |
| | 칩 높이 · 첫 칩 우변 | 26 · 264.7 | 26 · 264.7 | 26 · 264.7 | 26 · 264.7 | 26 | 26 |
| | 요약 줄 | `현대 · 1,000~2,000만 · 매각기일순 · 2/13페이지 · 필터 초기화` **2줄**(40px, ` · ` 에서만, 2차와 동일) | 1줄 | 1줄 | 1줄 | 1줄 | 1줄 |
구분 줄: `?sort=sale_date` 9~17페이지 순회 → **13페이지에만**(카드 높이 33, 표 33) `지난 기일 1,019건 — 낙찰은 결과 참고 · 유찰은 다음 기일 대기`. date URL 은 전부 지난 기일이라 1페이지 맨 위(`59건`).

### ③ 큰글씨(`naechaget:large=1`) 접힌 머리 — 높이 전부 30, `open=false`, 문서 가로 스크롤 0
| 첫 부품 | 폭 | 머리 텍스트 | span 폭 / 필요 폭 | 보이는 것(캡처) |
|---|---|---|---|---|
| 제조사(combo) | 360 · 320 | `검색 · 필터 — 현대 외 3` | 86 / 86 | 전부, `…` 없음 |
| 날짜(date) | 360 | `— 2026-09-01 매각 외 1` | 151 / 183 | `— 2026-09-01 매...` — **숫자 온전**, `각 외 1` 숨음 |
| 날짜 | 320 | 〃 | 111 / 183 | `— 2026-09...` — **숫자 안 절단** |
| 가격대(price) | 360 | `— 1,000~2,000만 외 1` | 151 / 166 | `— 1,000~2,000만...` — 숫자 온전 |
| 가격대 | 320 | 〃 | 111 / 166 | `— 1,000~2,...` — **숫자 안 절단** |

## 4. 캡처 — `screenshots/ux-round3/`(12장 md5 전부 상이, `HEAD.txt` 에 기준 커밋 `576de11`+dirty 목록·조건·md5)
| 파일 | 내용 | Read 확인 |
|---|---|---|
| `after-detail-640-pub.png` · `after-detail-768-pub.png` | 공개 뷰 헤더: `기아 카니발` 한 줄, 액션 줄 2줄(3+2 / 4+1), `다시 분석` 없음 | ✓ |
| `after-detail-768-admin.png` | 관리자 뷰 6버튼 4+2 | ✓ |
| `after-390-date-summary.png` · `after-320-date-summary.png` | 칩 `2026-09-01 매각 ✕` + 요약 줄 ISO 1줄 + 구분 줄(59건, 320 은 2줄) | ✓ |
| `after-390-split.png` | 13페이지 구분 줄 새 문구, 바로 아래 토레스 EVX(유찰 1회) | ✓ |
| `after-360-large-{combo,date,price}.png` · `after-320-large-{combo,date,price}.png` | 접힌 머리 부품 단위 — §3-③ | ✓(6장 전부) |

## 5. 테스트
- 신규 `tests/test_ux_round3.py`: **23 passed**(템플릿 7: 날짜·구분 줄·접힌 머리·all·라벨 소스·frame 소스·상세 CSS / Playwright 16: is-dirty 1·상세 헤더 6(공개·관리자 × 640·700·768)·frame 적대 5·frame 정상 1·저장 라벨 런타임 3). 첫 실행에서 상세 h1 단정이 6건 빨강 — 픽스처 이름 `현대 쏘나타(SONATA)` 가 192px 에서 두 줄(64) → qa 기준 물건과 같은 `기아 카니발` 로 바꾸고 h1 본문을 전제 단정(이름 길이를 재는 테스트가 되지 않게). 그 전엔 `document.querySelector('h1')` 이 헤더 밖 h1 을 잡아 null — 제목 열을 새 클래스로 직접 지목.
- 지시서 7파일(`test_ux_batch_qa_adversarial` 7 · `test_ux2_ux5_nav_state` 33 · `test_ux1_ux4_form_and_chips` · `test_ux3_sort_rules` · `test_feat1_price_select` · `test_feat1_qa_adversarial` · `test_price_band_filter`): **219 passed, 2 xfailed**(232.9s). 2차 212 + qa 7 = 219 ✓. xfail 5 → 2: qa 3건이 passed 로 옮겨 감(남은 2 = `test_feat1_qa_adversarial` 기존 strict xfail, 무변화).
- 전체 스위트(`NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1 python -m pytest -q -p no:cacheprovider`): **1차 `1551 passed, 2 xfailed, 0 failed`**(715.4s — 측정 스크립트·단일 파일 테스트와 병행해 느렸음; 로그 `scratchpad/pytest_full_round3.log`). 산술: qa 보고 1,528 + xfail→passed 3 + 신규 파일(이 실행 시작 시점 20건) = 1,551 ✓ · xfail 5 − 3 = 2 ✓. 그 뒤 저장 라벨 런타임 3건을 더해 **최종 재실행 `1554 passed, 2 xfailed, 0 failed`**(842.9s, 단독 실행이나 Windows 에서 Playwright 층이 느림; 로그 `scratchpad/pytest_full_round3_final.log`) = 1,551 + 3 ✓, 기대치와 일치. 남은 xfail 2 = `test_feat1_qa_adversarial` 기존 strict xfail(무변화). XPASS 0.
- 고친 기존 테스트: `test_ux2_ux5_nav_state.py` 4곳(사양 변경분만, 위 §1 끝) · `test_ux_batch_qa_adversarial.py` xfail 표식 3 제거 + 독스트링. 지운 테스트 0.

## 6. 못 한 것 · 남긴 것 · 판정 요청
1. **큰글씨 320 에서 첫 부품이 긴 조합의 숫자 절단**(§3-③) — critic 처방(첫 부품 + 외 N)의 CSS 만으로는 "첫 부품 자체가 안 들어가는" 경우를 못 막는다. 발생 조건: 320px 폰 + 큰글씨 + 제조사·판정 없이 날짜 또는 가격대만 건 목록(요약 줄·title 은 전문). 2차보다 나빠진 곳은 없다(2차는 모든 조합이 글자 단위 절단). 선택지(critic 판정 요청): ⓐ 현 상태 유지(360 이상 숫자 온전) ⓑ JS 로 "들어가는 부품까지만"(폰트 로드 뒤 측정, 첫 부품도 안 들어가면 머리에서 요약을 빼고 아래 요약 줄이 맡음 — 새 어휘 없음) ⓒ nc-large 에서 머리의 `filter_list` 아이콘 숨김(+26px, 360 가격대만 해결, 320 미해결). ⓑ 가 정답에 가깝지만 배포 전 마지막 수정에 JS 측정 로직을 넣는 위험 때문에 실행하지 않았다.
2. **검색 저장 라벨 전면 주입(한 원천)** — FEAT-1 ⑤ 단정 2개와 `최저가 ` 접두 판정을 바꿔야 가능. Steward 가 "저장 라벨도 칩과 완전히 같은 낱말(접두 없음, 곡선 따옴표)" 로 판정하면 `cond_parts = _cs.parts|list`(정렬·페이지 앞에서 스냅숏) 한 줄 주입으로 끝난다. 그때까지 q 의 직선 따옴표·`검사경과`(칩 `검사 경과`)·`seg` 손사전은 2차 그대로.
3. 구분 줄 320 에서 2줄(문구가 15자 길어짐) — keep-all 이라 낱말 절단 없음. 1줄로 만들려면 문구를 줄여야 해 critic 문구 그대로 둠.
4. 날짜 칩 pill 우변 320 에서 페이드 안 1.5px(✕ 글리프는 안) — 1·2차와 동일, 범위 밖.
5. 라이브 확인 없음(배포 대기). 스토어 캡처(`tools/store_final.py`)는 qa 가 적은 대로 배포 후 재촬영 대상.

## 7. 측정 조건
로컬 `127.0.0.1:52062`(`NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`, 8765·8888 LISTENING 무접촉, 금지 9포트 미사용). DB = `data/auction.db` 를 `mode=ro` 로 열어 `sqlite3.backup` 한 사본 `ux3.db`(1,418행, md5 `3530d885` = 1·2차·qa 사본과 동일; 공개 모수 1,163). Playwright Chromium headless, DPR 1, ko-KR, `has_touch=True`(1440 데스크톱 프레임 자동 리다이렉트 회피 — 900px 미만은 리다이렉트 조건 자체가 없음), 폰 높이 844·상세 900, `networkidle`+300ms, `getBoundingClientRect` 소수 1자리. 공개 뷰 = `X-Forwarded-For: 203.0.113.9` 헤더(qa 와 같은 방식), 관리자 = 헤더 없음. 오늘 = **2026-09-27**(측정 중 날짜가 넘어감 — 구분 줄 페이지가 13 그대로임을 9~17 순회로 확인). Playwright 테스트는 스레드 uvicorn + conftest tmp DB.

## 8. 확인된 사실 / 추정
**확인된 사실**: §1 앵커(`git diff`) · §3 수치(스크립트 JSON `measure_round3.json`, 캡처와 같은 세션) · 12장 md5 상이(`HEAD.txt`) · `all` 이 `vehicles.html` 컨텍스트에 없음(`TemplateResponse` dict 원문) · FEAT-1 ⑤ 가 `p.get('price')`·`'최저가 '+PB[pb]` 를 고정(테스트 원문) · pytest 출력 · `app.css` 규칙 810→818 · 운영 DB mtime 불변 · 8765 무접촉 · 320 큰글씨 숫자 절단(캡처 2장).
**추정**: 라이브(nginx 뒤) 공개 뷰가 XFF 흉내와 같은 렌더(qa 와 같은 근거 — `is_admin` 분기 하나) · 실제 폰에서 `URLSearchParams(FormData)` 지원(Chrome 49+/Safari 10.1+ — 헤드리스 Chromium 만 검증) · 선택지 ⓑ 의 구현 위험 평가.
