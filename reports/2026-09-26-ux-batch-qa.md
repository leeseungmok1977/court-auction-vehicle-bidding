# UX-1~5 묶음 — QA 적대적 반증 검증 (qa-engineer, 지시서 2026-09-26-24)

기준 커밋 `576de11` + 작업 트리 dirty(`web/app.py`·`web/db.py`·`web/static/{app.css,frame.html,tailwind_input.css}`·`web/templates/{base,detail,vehicles}.html`·`docs/backlog.md`,
untracked `reports/2026-09-26-ux{1-4,2-5,3}-*.md`·`tests/test_ux{1_ux4,2_ux5,3}_*.py`). 이 회차가 더한 파일: `tests/test_ux_batch_qa_adversarial.py`(신규 7건),
`screenshots/ux-batch-qa/`(37장 + `HEAD.txt`), 이 보고서. **코드 수정 0 · 커밋 0 · 배포·라이브 요청 0 · 운영 DB 쓰기 0 · 8765 무접촉.**

## [판정] 배포 가능(조건부) — 깨뜨린 것 1건(P2, 공개 뷰 640~768px 상세 헤더 회귀)을 배포 전에 한 줄로 고치기를 권고

A(탭 복귀)·B([적용] 보존·칩 ✕)·C(정렬·구분 줄)·E(PC 프레임)·F(회귀)·G(검색 저장) 주장은 전부 **못 깼다** — 아래 §2 에 조건과 수치.
D(공개 뷰 실측)에서 **1건을 깼다**: 상세 ← 에 `목록으로` 라벨이 붙어 액션 줄이 556→624px 이 되자, `flex-1`(basis 0) 제목 열이
**768px 공개 뷰에서 164→96px** 로 줄어 제목 `기아 카니발` 이 두 줄·법원/사건 줄이 두 줄→네 줄이 됐다(HEAD 는 한 줄·두 줄). 640~700 은
HEAD 에서도 이미 깨져 있었지만(36~96px, 낱글자 세로 배열) 이 묶음이 0~28px 로 **더 나쁘게** 했다. frontend 보고 §3-⑤ "들어갈 때(768 이상)는
렌더가 한 픽셀도 바뀌지 않는다" 는 **관리자 뷰(버튼 6개) 기준**이라 공개 뷰 768 을 놓쳤다(같은 보고 §7-4 가 구조를 '남긴 것'으로 적어 두긴 했다).
폰 폭(≤430)·PC 프레임(420px iframe)·1440 에는 영향 없음. 처방은 CSS 한 줄 수준(제목 열 최소 폭 또는 헤더 `flex-wrap` + 액션 줄 `basis-full lg:basis-auto`)
— app-design-expert 검수에서 어차피 잡힐 항목이므로 **배포 전 수정을 권고**하되, 오너가 후속으로 미뤄도 사용자 손해(금전·판정)는 없다.

기존 결함(이 묶음 무관, HEAD 도 동일) 3건은 §4 에 분리했다 — 그중 `frame.html` 해시 가드 우회(`#/\evil.com` → iframe 에 외부 사이트)는 **P2 보안 성격**이라 별도 티켓을 권한다.

## 1. 깨뜨린 것

### D-1 · 공개 뷰 640~768px 상세 헤더 — 제목 열이 0~96px 로 눌림 (P2 · 회귀)
- **재현**: 공개 뷰(`X-Forwarded-For` 헤더, 관리자 아님) · 뷰포트 768×900(또는 640·655·680·700) · `/vehicle/2025타경57868_1`(감정평가서·시세 있음 → 버튼 5개: 즐겨찾기·감정평가서·리포트·공유하기·목록으로).
- **기대**: 라벨 추가가 "768 이상 렌더 무변화"(frontend §3-⑤).
- **실제**(같은 DB 사본·같은 헤더, HEAD `detail.html` 만 런타임으로 갈아 끼운 8964 서버 vs 작업 트리 8963 — 리포 파일 무접촉):

| 폭 | 제목 열 폭 HEAD → 지금 | h1 높이(줄) HEAD → 지금 | 법원·사건 줄 높이 HEAD → 지금 | 액션 줄 폭 HEAD → 지금 |
|---|---|---|---|---|
| 640 | 36.4 → **0** | 64(2줄) → 64 | 160(8줄) → **480(24줄)** | 556 → 592(2줄 접힘) |
| 655 | 51.4 → **0** | 64 → 64 | 140 → **480** | 556 → 607 |
| 680 | 76.4 → **8** | 64 → 64 | 80 → **480** | 556 → 624 |
| 700 | 96.4 → **28** | 64 → 64 | 80 → **240** | 556 → 624 |
| 740 | 136.4 → 68 | 32(1줄) → **64(2줄)** | 60 → **100** | 556 → 624 |
| **768** | 164.4 → **96** | **32 → 64** | **40 → 80** | 556 → 624(1줄) |

- 캡처: `D3-detail-header-HEAD-pub-768.png`(제목 한 줄) vs `D3-detail-header-work-pub-768.png`(제목 두 줄·칩 세 줄·법원 줄 네 줄), `D-detail-actions-pub-640.png`(낱글자 세로 배열 — HEAD 도 이 폭은 깨져 있었음). md5 전부 상이(§5).
- **원인**: 상세 헤더 컨테이너는 `flex-nowrap`(sm 이상), 제목 열 `flex-1`(basis 0) vs 액션 줄 min-content 624. `sm:shrink-0` 제거는 **잘림**을 막았지만(넘침 0 확인) 제목 열이 남는 폭을 가져가는 구조는 그대로라 라벨 68px 이 곧장 제목에서 빠졌다.
- **넘침은 없다**: 7폭 전부 `row.scrollWidth ≤ clientWidth`, 자식 우변 ≤ 컨테이너 우변 ≤ vw, `#appscroll`·문서 가로 스크롤 0, `다시 분석` 버튼 부재(공개 뷰 확정). 640~655 의 "잘림" 주장(frontend 판단 ⑵)은 맞다 — 그 대가로 제목이 사라졌을 뿐이다.
- **처방(제안, 코드 미수정)**: 제목 열에 최소 폭(`min-w-[10rem]` 류) 또는 헤더를 `flex-wrap` 으로 두고 액션 줄을 `basis-full lg:basis-auto` 로 — 좁으면 액션 줄이 제목 **아래**로 내려간다. 고친 뒤 640·655·680·700·740·768 공개 뷰 재측정(이 표가 그대로 회귀 기준).

## 2. 못 깬 것 — 조건·수치

측정 조건(공통): 로컬 `127.0.0.1:8963`(`NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`, 금지 포트 미사용, 8765·8888 LISTENING 무접촉) · DB = `data/auction.db` 를 `mode=ro` 로 열어
`sqlite3.backup` 한 사본(1,418행, md5 `3530d885` = frontend·backend·FEAT-1 r2 사본과 동일; 공개 모수 1,163) · Playwright `channel="chrome"` 153 headless · DPR 1 · ko-KR ·
폰 = `is_mobile`+`has_touch` 390×844 / 360×844 · 공개 뷰 = `extra_http_headers={"X-Forwarded-For":"203.0.113.9"}` · 오늘(SQL `date('now','localtime')` = 파이썬) = 2026-09-26 · 사본에 `sale_date = 오늘` 0행.
원자료: 스크래치 `a_result.json`·`a2_result.json`·`b_result.json`·`b2_result.json`·`c_result.json`·`d_result.json`·`d2_result.json`·`d3_result.json`·`e_result.json`·`e2_result.json`·`g_result.json`·`f_result.json`.

### A. 탭 복귀형(UX-2) — 워크스루 S1·S3·S7·S8·S11 재현: **12/12 '유지'** (M390·M360)
| 단계 | M390 | M360 | 비고 |
|---|---|---|---|
| S1-07 달력→탭 | URL·셀렉트 3(현대/1000-2000/sale_date)·2페이지(13–24/146)·scrollTop **2088→2088** | 2105→2105 | 캡처 `A-S1-07-return-{390,360}.png` |
| S1-09 홈→탭 | 유지, scrollTop 2088 | 유지 2105 | |
| S1-11 즐겨찾기→탭 | 유지 2088 | 유지 2105 | |
| S3-18 상세 [목록으로] | 유지, scrollTop 275 | 275 | ⚠ 275 는 **내 스크립트 조건**: Playwright 가 `.first` 카드를 뷰포트로 스크롤한 뒤 클릭해 저장값이 275 로 바뀌었다. 복원값 = 저장값 → 유지 |
| S3-20 상세→탭 | 유지 275 | 275 | 캡처 `A-S3-20-detail-tab-*.png`, 상세 캡처 `A-S3-17-detail-*.png`(← 라벨 `목록으로` 확인) |
| S7-39 미적용 변경 후 탭 | `/vehicles`, 제조사 '' — 설계대로(미적용 변경은 사라짐, is-dirty 는 켜져 있었음) | 동일 | 예전과 같은 동작 |
| S8-45 큰글씨 · mileage 적용 후 탭 | URL·`sort=mileage` 유지 | 유지 | 접힌 머리 `검색 · 필터 — 현대 · 1,000~2,000만 · 매각기일순 · 필터 초기화` 캡처 `A-S8-41-*` |
| S11 picks=1 → 현대 적용 | `picks=1` 유지, 4→4 | 동일 | |
| S11 bucket=lowconf → 현대 | 유지, 68→22 | 동일 | |
| S11 segment=suv&upcoming=30 → 현대 | **유지, 36→7**(라이브 재현 대상 S11-54→55 "≤88" 의 사본판) | 동일 | |
| S11-56→57 date=2026-09-01 → mileage | **`date` 유지, 59→59** | 동일 | 캡처 `A-S11-57-date-kept-*.png` |

공격 결과(M390):
| # | 공격 | 결과 |
|---|---|---|
| ① `nc:lastList` 주입 12종 | `javascript:`·`//evil.com/x`·`/vehicle/…`·`http://evil.com/vehicles`·잘못된 JSON·`ts` 31분 전·`ts` 문자열 → **전부 `/vehicles`**, alert 0. `ts` 미래(+1h) → 저장 URL 로 이동(만료 아님으로 처리 — 같은 출처 목록 URL 이라 무해). **약점(비차단)**: 접두 검사 `indexOf('/vehicles')===0` 라 `/vehiclesfoo`→404, `/vehicles\@evil.com`→`/vehicles/@evil.com`(404), `/vehicles/../admin`→**`/admin`**(같은 출처). sessionStorage 는 같은 출처 스크립트만 쓸 수 있어 XSS 없이는 못 심는다 — 결함 아님, 다만 `new URL(u, origin).pathname === '/vehicles'` 로 좁히면 깔끔하다 |
| ② 히스토리 | 목록(2p)→상세→탭→목록: `back`→상세, `back`→목록(2p), `forward`→상세 — **꼬임 없음**(탭 복귀는 `location.assign` 이라 히스토리에 정상 push) |
| ③ 스크롤 복원 플래그 | 탭 복귀 뒤 `nc:restoreScroll` = null(소비됨), 홈 → `location.assign(같은 URL)`(nav type `navigate`) → scrollTop **0**(복원 안 함) |
| ④ is-dirty 상태로 재탭 | 이동 없음·URL 불변·scrollTop 0·바꾼 셀렉트(기아) 유지·is-dirty 유지 — 캡처 `A-attack4-dirty-retap-390.png` |
| ⑤ JS 끔 | 탭 앵커 `href="/vehicles"` 그대로(HTML 폴백). ⚠ JS 가 꺼지면 `#splash` 오버레이가 안 걷혀 **포인터 클릭 자체가 막힌다**(`splash-done` 을 JS 가 붙임) — 기존 동작, 이 묶음 무관. 캡처 `A-attack5-jsoff-calendar-390.png` |
| ⑥ 사이드바(1440 관리자) | 달력→사이드바 `차량 목록` → URL·2페이지 유지, scrollTop 441(>0, 저장 시점 값은 따로 안 찍음) |
| ⑦ Ctrl+클릭 | 새 탭 `/vehicles`, 현재 탭 `/calendar` 그대로 — 수정키는 기본 동작 |
| ⑧ 다른 탭에서 목록 B 를 본 뒤 | 상세 ← href(서버 쿠키)와 하단 탭(sessionStorage) 모두 목록 A — 이 시나리오에선 일치. 두 손잡이가 **다른 원천**을 보는 구조는 설계(쿠키 = 기기 공유, sessionStorage = 탭 단위) — 결함으로 올리지 않음 |

### B. [적용] 파라미터 보존(UX-1) — 진입 파라미터 25조합 × 셀렉트 1개 변경: **DoD 전 종류 유지, 총수 논리적, 중복 키 0**
폼을 HTMLParser 로 파싱(셀렉트 selected/첫 옵션·hidden·search)해 브라우저 GET 제출을 재현, 공개 뷰. `segment`(265→88)·`segment&upcoming`(36→7)·`date`(정렬 변경 47→47 / 제조사 47→10)·
`court` 단일(166→49)·**다중 콤마 그대로**(247→76)·`court&upcoming&sort`(22→22)·`promising`(372→146)·`bucket`(68→22 / 827→827)·`usepick` 1/now/cheap·`picks`(4→4)·`upcoming`(144→42)·
`cond` 2종·`result`(248→66)·`price`(418→146)·`q`(20→9 / 20→19)·`judgment&sort=expected`(7→0)·`status`(908→309). 조건을 더 걸었는데 늘어난 경우 **0**.
칩 ✕ — 12키 전부 실은 URL 에서 날짜·결과·법원(2곳)·검색어·가격대·입찰예정·검사경과·버킷 칩 href 가 **그 키 하나만** 빼고 11키 유지(parse_qs 비교). 모수 0 이 아닌 4조합에서 각 칩을 **실제로 열어** 총수 ≥ 이전(예: 법원 2곳 ✕ 1→7, 가격대 ✕ 1→4, 입찰예정 ✕ 1→14, 검사 경과 ✕ 1→2, 결과=유찰 ✕ 5→15, 수원지법 ✕ 5→27, “카니발” ✕ 5→58). `court` 다중값 ✕ 는 **법원 조건 전부**를 뺀다(칩 문구 `법원 2곳 ✕` 과 일치). `외관 손상 ✕` 는 maker·price 유지. `실사용 추천 ✕`·`유망 물건 ✕` 는 예전부터 `/vehicles`(전부 초기화) — DoD 밖, 변경 없음.

### C. 정렬(UX-3) — 사본 전 페이지 순회: **어디서도 깨지지 않음**
- DB 층(`db.list_vehicles(sort="sale_date")`): hide_incomplete 1,163 = 미래 144 · 과거 1,019 · NULL 0 / 전체 1,418 = 233·1,183·2 / upcoming=30 144 / 현대×1,000~2,000만 146 = 16·130 — 4조합 모두 [블록 단조][미래 ASC][과거 DESC] True. 첫 3행 `2026-09-28`(예전 식 `2026-08-18`).
- 라우트 층(공개 뷰, 카드 id 순서를 DB sale_date 로 대조): `sort=sale_date` **97페이지 1,163장 전부**·중복 0·구분 줄 **정확히 1회(13페이지 0번, 앞 카드 없음·뒤 카드 2026-09-23)** = backend 계약(전역 144). `upcoming=30` 12페이지 구분 줄 0 · 현대×1000-2000 13페이지 → 2페이지 4번(앞 `2026-10-01`·뒤 `2026-09-23`) · `result=낙찰` 21페이지 → 1페이지 0번(전부 과거) · `segment=suv` 23페이지 → 4페이지 0번 · `bucket=wait` 69페이지 → 7페이지 5번 · `all=1` 119페이지(NULL 2 포함, 맨 뒤) → 20페이지 5번 · `date=2026-09-29` 0회 · `date=2026-09-21`(과거만) → 1페이지 0번. 카드 섹션과 표 섹션의 구분 줄 수 매 페이지 일치. 브레이크포인트별 **실제 렌더된** 구분 줄 1개(320·390 카드 div h33, 1440 표 tr h33; 앞·뒤 형제 = 카드) — 캡처 `D-list-split-boundary-pub-390.png`.
- 구분 줄 없어야 하는 곳: `usepick=1`·`picks=1`·`sort=expected`·`sort=recent`·`sort=sale_date_asc`(내부 키를 URL 로) 전부 0.
- `sort=mileage` 1페이지 `[1, 986, 1374, 2311, …, 8229]` — 0·NULL 없음; DB 층 양수 1,087 오름차순·뒤 76행 NULL/0.
- **오늘 경계**: 사본 0행 → tmp DB 테스트로 고정(`test_today_is_first_of_upcoming_block_and_split_sits_before_first_past`): [오늘, +1, +3, 구분 줄, −1, −2], `sale_split={upcoming 3, past 2, undated 0, idx 3}` 초록.
- `list_vehicles` 기본값 `sale_date_asc`: 사본에서 `sort` 미지정 결과가 예전 `ORDER BY sale_date` 와 동일(첫 3행 `2026-08-18`). 호출부 grep: `web/service.py` 40여 곳·`web/app.py` 4곳·`tools/{monthly,weekly}_report.py` 전부 sort 미지정 → 무영향. **`sort="sale_date"` 를 명시하는 파이썬 호출부 0**. `/watchlist` 는 `sort` 를 받지만 파이썬 `rows.sort(key=…)` 로 따로 정렬해 `list_vehicles` 변경이 닿지 않음. 템플릿 링크 8곳(`dashboard`·`calendar`·`courts`)과 `tools/capture_store_shots.py` `HERO_LISTS` 의 `/vehicles?sort=sale_date` 는 새 순서를 **의도대로** 받는다 — ⚠ 스토어 캡처는 배포 후 `tools/store_final.py` 재실행 대상(첫 화면이 낙찰 종료→예정 기일로 바뀜).

### D. 공개 뷰 실측(frontend 가 못 한 것) — 7폭(320·360·390·430·640·768·1440), XFF 헤더, `다시 분석` 부재 확정
- 상세 액션 줄(5버튼): 넘침 **7/7 없음**(줄·자식·`#appscroll`·문서 가로 스크롤 전부 0). 320·360 = 3줄(142px), 390·430·640 = 2줄(92px), 768·1440 = 1줄(42px, 줄 폭 624 — frontend 산술 623 과 1px 차). **단 제목 열은 §1 D-1.** 캡처 `D-detail-actions-pub-{320,390,640,768,1440}.png`.
- 목록 4 URL × 7폭: 가로 스크롤 0/28, 활성 칩 높이 = 이웃 26 **불일치 0**(날짜·검색어·법원 2곳·가격대·입찰예정·검사 경과), 관리자 표식 0. 320 첫 활성 칩: 가격대 264.7·검색어 229.5·법원 228 < 페이드 275 통과; **날짜 칩만 pill 우변 278.1(09-29)/276.5(09-01) > 275 — ✕ 글리프 우변 265.1/263.5 로 글리프는 10~12px 안**(DoD "해제 ✕ 첫 화면 안" 충족, frontend 1차 §5-3 이 적은 1.5px 가 두 자리 날짜에선 3.1px). 요약 줄 320 combo 2줄(40px, ` · ` 에서만 접힘) 그 외 1줄, 넘침 0. sm 미만 `필터 초기화` 는 요약 줄 끝, sm 이상은 칩 줄(`reset_chip_visible` 640+ True). 캡처 `D-list-{date,court,combo_p2,split}-pub-{320,390,1440}.png`.

### E. PC 프레임(UX-4/U4) — 1440 마우스 컨텍스트 + XFF(공개 데스크톱 경로)
`/vehicles?maker=현대&price=1000-2000` → **자동 리다이렉트 `/static/frame.html#/vehicles?…`** 확인(관리자 loopback 은 리다이렉트 없음도 확인). 프레임 안 페이지 [2] → 바깥 해시 `…&page=2`(iframe URL 과 일치) · 카드 → `#/vehicle/2025타경31471_1` 일치 · 프레임 안 하단 탭 `차량목록` → 마지막 목록(2페이지) 해시 일치 · `page.reload()` → iframe **`page=2`·`price=1000-2000` 유지**(캡처 `E-frame-1440-after-reload-pub.png`, 요약 줄 `현대 · 1,000~2,000만 · 2/13페이지`) · `page.go_back()` → **타임아웃 없이** iframe 이 직전 항목(상세)으로 되감기고 바깥 해시가 따라옴(S9b-04 미검증 항목 해소, 조건: reload 직후 조인트 히스토리).
해시 주입(매번 `about:blank` 거쳐 새 문서): `#//evil.com/x`·`#javascript:alert(1)`·`#http://evil.com/`·`#/%2F%2Fevil.com`·깨진 `%E2%82` → iframe `/`, 외부 요청 0. **`#/\evil.com/x`·`#/\\evil.com` → iframe src `/\evil.com/x` 가 `http://evil.com/x` 로 풀려 외부 요청 발생** — §4-3(HEAD 가드 그대로, 이 묶음 무관; 새 `load` 리스너는 교차 출처 접근이 throw 되어 해시를 건드리지 않음 — 악화 없음).

### F. 회귀
- 전체 스위트 `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1 python -m pytest -q -p no:cacheprovider`: **1차(내 테스트 추가 전) 1524 passed, 2 xfailed, 0 failed(376s — 다른 작업과 병행)** = frontend 보고와 동일. **2차(신규 7건 포함)**: 아래 §5.
- `web/static/app.css` 규칙 단위 diff(HEAD 709 → 715 규칙): **추가만** — `.-my-2\.5`·`.min-h-\[40px\]`·`.max-w-\[9rem\]`·`.leading-5`·`.btn-ghost.is-dirty`·`.btn-ghost.is-dirty:hover`, `@media (min-width:640px)` 블록 안 `.sm\:inline-flex` 1개 추가. **삭제·변경 0.**
- `tailwind_input.css` +4줄 = 주석 2줄 + `.btn-ghost.is-dirty{background:#533afd;color:#fff;border-color:transparent}` + `:hover{background:#4434d4}`(`.btn-primary` 토큰과 동일).

### G. 검색 저장 라벨 — 공개 뷰 390, 저장 → `naechaget:searches` → `/api/vehicles/count` → 즐겨찾기 카드 → 카드 클릭
| 조건 | 목록 총수 | 저장 라벨 | qs 유지 | count API | 즐겨찾기 카드 |
|---|---|---|---|---|---|
| `q=쏘나타` | 20 | `"쏘나타"` | ✓ | 20 | `"쏘나타" 저장 시 20건 · 현재 20건` |
| `court=수원,인천&upcoming=30` | 22 | `법원 지정 · 입찰예정 30일` | ✓(콤마 다중 그대로) | 22 | 현재 22건 |
| `court=수원&q=카니발` | 15 | `"카니발" · 법원 지정` | ✓ | 15 | 현재 15건, 카드 클릭 → 같은 URL·15 |
| `date=2026-09-29&sort=sale_date` | 47 | **`전체 물건`** | ✓ | 47 | `전체 물건 저장 시 47건 · 현재 47건` — 라벨만 거짓(§4-2, 기존) |
캡처 `G-watchlist-saved-pub-390.png`.

## 3. 새 코드의 약점(비차단, 기록)
1. `nc:lastList` 접두 검사(§2-A ①): 같은 출처 경로 이탈(`/vehicles/../admin`). 원천이 sessionStorage 라 위협 모델 밖 — 다음 손질 때 `URL` 파싱으로.
2. 저장 URL 의 `ts` 가 미래면 만료로 보지 않음 — 기기 시계가 뒤로 가면 30분 TTL 이 길어질 뿐.
3. 날짜 칩 pill 우변이 320 에서 페이드 안 1.5~3.1px(✕ 글리프는 안) — frontend 가 이미 적음.

## 4. 기존 결함 — 이 묶음 무관(HEAD 도 동일), 분리 권고
1. **`?all=1` 진입 → [적용] 이 `all` 을 버린다** — hidden 7+4종에 `all` 없음(HEAD 도 없음). 1,418→377(현대) 처럼 모수(불완전 포함/제외)가 조용히 바뀐다. UX-1 DoD 4종 밖. P3, `{% if all %}` hidden 한 줄. strict xfail `test_form_keeps_all_param_on_apply`.
2. **검색 저장 라벨이 `date`(·result·status·bucket·usepick·picks·promising)를 안 읽어 `전체 물건`으로 찍힌다** — qs·건수는 맞으므로 동작은 정상, 이름표만 거짓. HEAD `ncSaveSearch` 부품 목록 동일. P3. strict xfail `test_saved_search_label_reads_date`.
3. **`frame.html` 해시 가드 우회** — `#/\evil.com` 이 `iframe.src="/\evil.com"` 으로 들어가고 브라우저가 `\`→`/` 로 정규화해 `//evil.com`(외부)을 폰 프레임 안에 띄운다(피싱 벡터, 클릭 한 번). 가드 `!p.startsWith("/") || p.startsWith("//")` 는 HEAD 그대로. 서버 `back_url` 검사(`_bk.startswith("/") and not "//"`)도 같은 모양이지만 값 원천이 서버 쿠키라 위험 낮음. **P2 보안 성격 — 별도 티켓 권고**(처방: `new URL(p, location.origin).origin === location.origin` 또는 `\` 거부). strict xfail `test_frame_hash_guard_rejects_backslash_or_checks_origin`.
4. JS 끔에서 `#splash` 오버레이가 남아 아무것도 못 누른다(§2-A ⑤) — 앱이 JS 전제라 결함으로 올리지 않음, 기록만.

## 5. 테스트
- 신규 `tests/test_ux_batch_qa_adversarial.py`: **4 passed, 3 xfailed(strict)** — ① 오늘 경계 2건 ② 칩 7종 실제 추적 1건(FULL 조건 모수 ≥1 을 먼저 단언해 공허 통과 방지) ③ `nc:lastList` 적대 7종 Playwright 1건(ts 를 브라우저에서 `Date.now()` 로 덮어 만료 때문에 통과하는 공허 통과 방지) ④ 기존 틈 3건 strict xfail.
- 지운 기존 테스트 0 · 고친 기존 테스트 0. 수는 늘기만 했다(1,415 지시서 기준 → 1,524 → 1,531 수집).
- **전체 스위트 2차 실제 수(신규 7건 포함): `1528 passed, 5 xfailed, 0 failed`** (649.6s — Playwright 측정 스크립트와 병행해 느렸음; 1차 1,524+4 = 1,528, xfail 2+3 = 5 로 산술이 맞는다. 실행 로그 `scratchpad/pytest_full_2.log`).

## 6. 확인된 사실 / 추정
**확인된 사실**: §1 표(두 서버 동시 실측, 캡처 4장 md5 상이) · §2 전 수치(스크립트 JSON) · 37장 캡처 md5 **전부 상이**(중복 0) · 운영 DB `mode=ro`+backup 사본만 사용 · `git status` 가 내 신규 3항목(테스트·캡처·보고서) 외에 늘지 않음 · 8765 무접촉 · 1차 스위트 1524/2.
**추정**: ⑴ 라이브(nginx 뒤) 공개 뷰가 XFF 흉내와 같은 렌더일 것(`is_admin` 분기 하나뿐이라 근거 강함) ⑵ D-1 의 처방이 한 줄로 끝날 것(구현·재측정 전) ⑶ 스토어 캡처 첫 화면 변화(재촬영 전).
