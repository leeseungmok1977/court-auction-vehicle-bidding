# 차량 목록 검색·필터 사용성 — 실제 클릭 워크스루 (상태 유지 중심)

- 지시서 2026-09-26-17 / 실행 `app-qa-auditor` / 정리 Steward(담당의 보고서 파일 저장이 권한에서 막혀, 담당이 넘긴 본문을 Steward 가 그대로 옮겼다. 단계 표는 담당의 `table-compact.md` 원본).
- 라이브 `https://naechaget.co.kr` 비로그인 공개 뷰 · 2026-09-26 20:34–20:50 KST · Playwright Chromium 148 · 모든 수치는 DOM 읽기, 단계 표는 JSON 에서 스크립트 생성.
- 근거: `screenshots/search-ux/` 98장 + `HEAD.txt`(라이브 배포 `3c64dd7` 20:17, 로컬 HEAD `6704728`) + `steps.json`(95단계 원자료).
- **Steward 재현(2026-09-26)**: U1 `web/app.py` `set_cookie("last_list", …)` 3곳·상세 `request.cookies.get("last_list")` 확인, 탭 매크로 `tab('/vehicles', …)` 쿼리 없음 · U2 `vehicles.html` hidden 은 `upcoming/result/status/cond/bucket/usepick/picks` 7종만(segment·date·court·promising 없음) · U3 활성 칩 3종 전부 `whitespace-nowrap` 없음, `S11-56-enter-date-M390.png` 에서 날짜 칩 3줄 육안 확인 · U1 복귀 화면 `S1-07-back-from-경매 달력-M390.png` 전체 1,316건·최근 등록순 육안 확인 · U5 `db.py` `sort_cols` 에서 `sale_date` 는 방향 없는 오름차순(지난 기일이 앞, `recent` 만 DESC).

## 1. [요약]
1. **유지되는 것**: 상세 [뒤로] 버튼(`history.back()`)과 브라우저 뒤로가기 — 필터·정렬·2페이지·`#appscroll` 스크롤(2227px)까지 그대로 복귀(M390·D1440, `nav=back_forward`). 검색 저장 → 즐겨찾기 카드 → 같은 필터·같은 총수(159=159). 퀵 칩 토글·가격대 해제 칩은 다른 필터와 검색어를 보존.
2. **안 되는 것**: 하단 탭/사이드바 `차량목록`으로 돌아오면 **필터·페이지·스크롤 전부 초기화** — 3컨텍스트 × (달력·홈·즐겨찾기·상세) 왕복 12회 전부 미유지. 설계 ①이지만 서버는 이미 `last_list` 쿠키를 갖고 있다. PC 프레임 F5 는 첫 경로로 되돌아간다.
3. **버그(설계 아님)**: 셀렉트 [적용]이 `segment`(차종)·`date`(달력 날짜) 파라미터를 버린다 — `bucket`·`picks`·`upcoming`은 hidden 으로 남는데 이 둘만 빠져 88→128건, 28→1,316건으로 모수가 조용히 바뀐다. 활성 칩 `입찰예정 30일 ✕`(2줄)·`2026-09-01 매각 ✕`(3줄)이 390px 에서 줄바꿈.
4. **가장 불편한 것 1개**: 필터 걸고 2페이지까지 내려갔다가 달력을 한 번 보고 `차량목록` 탭을 누르면 **처음부터 다시** — 셀렉트 3개 + [적용] + 페이지 + 스크롤을 매 왕복마다 반복(S1-07/09/11, S3-20, S8-45).

## 2. [단계 기록]
Ctx: M390=390×844 폰 · M360=360×780 폰 · D1440=1440×900 PC(`/static/frame.html#…` 420px iframe 안에서 조작). 판정: 유지/미유지/부분. `-`=목록 화면 아님.
⚠ M390 S4-21~23 의 "검색어" 열은 헤더의 숨은 `input[name=q]` 를 먼저 읽은 **측정 오류**(빈값). 실제는 URL `q=쏘나타` 와 M360 S4-12~14 재측정(`쏘나타` 유지)으로 확인 — 제품 결함 아님.

| Ctx | 단계 | 누른 것 | URL 후 | 제조사/가격대/정렬 | 검색어 | 활성 칩 | 총 | 페이지 | scrollTop | 스크린샷 | 판정·비고 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M390 | S1-01 | 직접 진입 /vehicles | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-01-list-initial-M390.png |   |
| M390 | S1-02 | 셀렉트 3개 선택(현대 / 1,000~2,000만 (451) / 매각기일순), 적용 안 | `/vehicles` | 현대/1000-2000/sale_date | - | - | 1316 | 1 | 0 | S1-02-selects-set-before-apply-M390.png |   |
| M390 | S1-03 | [적용] | `/vehicles?maker=현대&price=1000-2000&sort=sale_date` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S1-03-after-apply-M390.png |   |
| M390 | S1-04 | 페이지 번호 [2] | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 0 | S1-04-page2-M390.png |   |
| M390 | S1-05 | #appscroll 절반 스크롤(scrollTop=2227) | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S1-05-page2-scrolled-M390.png |   |
| M390 | S1-06 | 하단 탭 [calendar_month 경매달력] | `/calendar` | - | - | - | - | - | 0 | S1-06-at-경매 달력-M390.png |   |
| M390 | S1-07 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-07-back-from-경매 달력-M390.png | 미유지 경매 달력→차량목록 탭 복귀:  |
| M390 | S1-08 | 하단 탭 [home 홈] | `/` | - | - | - | - | - | 0 | S1-08-at-대시보드-M390.png |   |
| M390 | S1-09 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-09-back-from-대시보드-M390.png | 미유지 대시보드→차량목록 탭 복귀:  |
| M390 | S1-10 | 하단 탭 [star 즐겨찾기] | `/watchlist?ids=&sort=sale_date` | - | - | - | - | - | 0 | S1-10-at-즐겨찾기-M390.png |   |
| M390 | S1-11 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-11-back-from-즐겨찾기-M390.png | 미유지 즐겨찾기→차량목록 탭 복귀:  |
| M390 | S2-12 | 필터+2페이지+스크롤(2227) 준비 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S2-12-state-page2-scrolled-M390.png |   |
| M390 | S2-13 | 하단 탭 [calendar_month 경매달력] | `/calendar` | - | - | - | - | - | 0 | S2-13-at-calendar-M390.png |   |
| M390 | S2-14 | 브라우저 뒤로가기 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S2-14-browser-back-M390.png | 유지 달력→브라우저 back:  |
| M390 | S2-15 | 예외(스크립트)  Locator.click: Timeout 30000ms excee | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S2-15-EXC-M390.png | 오류  |
| M390 | S3-16 | 필터+2페이지+스크롤(2227) 준비 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S3-16-state-page2-scrolled-M390.png |   |
| M390 | S3-17 | 화면에 보이는 카드(#19) 탭 | `/vehicle/2025타경10074_1` | - | - | - | - | - | 0 | S3-17-detail-M390.png |   |
| M390 | S3-18 | 상세 [뒤로] 버튼 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S3-18-detail-backbtn-M390.png | 유지 상세 뒤로버튼:  |
| M390 | S3-19 | 같은 카드(#19) 탭 | `/vehicle/2025타경10074_1` | - | - | - | - | - | 0 | S3-19-detail-again-M390.png |   |
| M390 | S3-20 | 상세에서 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S3-20-detail-tab-vehicles-M390.png | 미유지 상세→차량목록 탭:  |
| M390 | S4-21 | 검색창 '쏘나타' → [적용] | `/vehicles?sort=recent쏘나타` | 전체/전체/recent | - | - | 20 | 1 | 0 | S4-21-q-sonata-M390.png | 미유지 검색어='' 총=20 칩=[] input.type=text / 검색어 해제 칩 존재=False |
| M390 | S4-22 | 가격대 1,000~2,000만 (9) 추가 → [적용] | `/vehicles?price=1000-2000&sort=recent쏘나타` | 전체/1000-2000/recent | - | 1,000~2,000만 ✕ | 9 | 1(단일) | 0 | S4-22-q-plus-price-M390.png | 부분 검색어='' 가격대='1000-2000' 총=9 칩=['1,000~2,000만 ✕'] |
| M390 | S4-23 | 가격대 해제 칩 [✕] | `/vehicles?q=쏘나타&sort=recent` | 전체/전체/recent | (측정오류: URL q=쏘나타) | - | 20 | 1 | 0 | S4-23-price-chip-removed-M390.png | 미유지 검색어='' 가격대='' 총=20 |
| M390 | S4-24 | 검색창 비우고 [적용] | `/vehicles?sort=recent` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S4-24-q-cleared-apply-M390.png | 유지 검색어='' 총=1316 (검색어만 지우는 ✕ 없음 → 비우고 적용이 유일 경로) |
| M390 | S5-25 | 현대 + 1,000~2,000만 (451) → [적용] | `/vehicles?maker=현대&price=1000-2000&sort=recent` | 현대/1000-2000/recent | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S5-25-combo-M390.png |   |
| M390 | S5-26 | [검색 저장] | `/vehicles?maker=현대&price=1000-2000&sort=recent` | 현대/1000-2000/recent | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S5-26-save-clicked-M390.png |  alert=['검색을 저장했습니다.\n즐겨찾기 탭 → 저장한 검색에서 새 매물을 확인하세요.'] / localStorage=[ |
| M390 | S5-27 | 하단 탭 [star 즐겨찾기] → 저장한 검색 카드 | `/watchlist?ids=&sort=sale_date` | - | - | - | - | - | 0 | S5-27-watchlist-saved-M390.png |  카드='현대 · 최저가 1,000~2,000만 저장 시 159건 · 현재 159건 ✓ ✕' href=/vehicles?judg |
| M390 | S5-28 | 저장한 검색 카드 탭 | `/vehicles?maker=현대&price=1000-2000&sort=recent` | 현대/1000-2000/recent | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S5-28-saved-card-open-M390.png | 유지  |
| M390 | S6-29 | 현대 + 1,000~2,000만 (451) + 매각기일순 → [적용] | `/vehicles?maker=현대&price=1000-2000&sort=sale_date` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S6-29-filters-M390.png |   |
| M390 | S6-30 | 칩 [입찰예정 30일만] 켬 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&upcoming=30` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕, 입찰예정 30일 ✕ | 51 | 1 | 0 | S6-30-upcoming-on-M390.png | 유지  |
| M390 | S6-31 | 칩 [입찰예정 30일 ✕] 끔 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S6-31-upcoming-off-M390.png | 유지  |
| M390 | S6-32 | 칩 [검사 경과] 켬 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&cond=insp_expired` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕, 검사 경과 ✕ | 75 | 1 | 0 | S6-32-insp-on-M390.png | 유지  |
| M390 | S6-33 | 칩 [검사 경과 ✕] 끔 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S6-33-insp-off-M390.png | 유지  |
| M390 | S6-34 | 페이지 [2] | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 0 | S6-34-page2-M390.png |   |
| M390 | S6-35 | 2페이지에서 칩 [입찰예정 30일만] | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&upcoming=30` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕, 입찰예정 30일 ✕ | 51 | 1 | 0 | S6-35-page2-chip-toggle-M390.png | 확인 페이지=1 총=51 url=/vehicles?maker=%ED%98%84%EB%8C%80&sort=sale_date&price |
| M390 | S7-36 | 초기 화면 — [적용] 위치 | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S7-36-initial-applybox-M390.png |  applyBox={'top': 181, 'bottom': 223, 'vh': 844} firstCardTop=0 |
| M390 | S7-37 | 제조사 [기아] 선택만(적용 안 함) | `/vehicles` | 기아/전체/recent | - | - | 1316 | 1 | 0 | S7-37-select-changed-no-apply-M390.png |  applyBox={'top': 181, 'bottom': 223, 'vh': 844} total=1316 (변경 알림/자동제출 |
| M390 | S7-38 | 적용 없이 하단 탭 [calendar_month 경매달력] | `/calendar` | - | - | - | - | - | 0 | S7-38-left-to-calendar-M390.png |  dialogs=[] |
| M390 | S7-39 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S7-39-back-to-list-M390.png | 미유지 제조사='' — 적용 안 한 변경 (알림 없이) 사라짐 |
| M390 | S8-40 | 현대 + 1,000~2,000만 (451) + 매각기일순 → [적용] (일반 모드) | `/vehicles?maker=현대&price=1000-2000&sort=sale_date` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S8-40-filters-normal-M390.png |   |
| M390 | S8-41 | 헤더 [큰글씨] 켬 | `/vehicles?maker=현대&price=1000-2000&sort=sale_date` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S8-41-large-on-M390.png |  filterOpen=False summary='filter_list 검색 · 필터 expand_more' summaryVisi |
| M390 | S8-42 | 접힌 필터 머리 탭(펼침) | `/vehicles?maker=현대&price=1000-2000&sort=sale_date` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S8-42-large-expanded-M390.png |  filterOpen=True |
| M390 | S8-43 | 정렬 [짧은 주행거리순] → [적용] | `/vehicles?maker=현대&price=1000-2000&sort=mileage` | 현대/1000-2000/mileage | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S8-43-large-applied-M390.png |  filterOpen=False sort=mileage — 적용 후 다시 접힘? |
| M390 | S8-44 | 하단 탭 [calendar_month 경매달력] | `/calendar` | - | - | - | - | - | 0 | S8-44-large-calendar-M390.png |   |
| M390 | S8-45 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S8-45-large-back-M390.png | 미유지  |
| M390 | S8-46 | 헤더 [큰글씨] 끔 | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S8-46-large-off-M390.png |  filterOpen=True large=False |
| M390 | S11-49 | 직접 진입 / | `/` | - | - | - | - | - | 0 | S11-49-dashboard-M390.png |   |
| M390 | S11-50 | 대시보드 링크 탭: 유망 물건 전체 보기(picks=1) | `/vehicles?picks=1` | 전체/전체/recent | - | 유망 물건 11 ✕ | 11 | 1(단일) | 0 | S11-50-enter-picks-1-M390.png |  칩=['check_circle유망 물건 11 ✕'] 차종활성=['전체'] 총=11 정렬='recent' |
| M390 | S11-51 | 제조사 [현대] → [적용] | `/vehicles?maker=현대&sort=recent&picks=1` | 현대/전체/recent | - | 유망 물건 11 ✕ | 11 | 1(단일) | 0 | S11-51-apply-picks-1-M390.png | 유지 카드에서 온 파라미터 picks=1 → 적용 후 URL=/vehicles?judgment=&maker=%ED%98%84%EB% |
| M390 | S11-52 | 대시보드 링크 탭: 집계 카드 신뢰도 낮음(bucket=lowconf) | `/vehicles?bucket=lowconf` | 전체/전체/recent | - | 신뢰도 낮음 108 ✕ | 108 | 1 | 0 | S11-52-enter-bucket-lowconf-M390.png |  칩=['신뢰도 낮음 108 ✕'] 차종활성=['전체'] 총=108 정렬='recent' |
| M390 | S11-53 | 제조사 [현대] → [적용] | `/vehicles?maker=현대&sort=recent&bucket=lowconf` | 현대/전체/recent | - | 신뢰도 낮음 35 ✕ | 35 | 1 | 0 | S11-53-apply-bucket-lowconf-M390.png | 유지 카드에서 온 파라미터 bucket=lowconf → 적용 후 URL=/vehicles?judgment=&maker=%ED%98 |
| M390 | S11-54 | 대시보드 링크 탭: 차종 카드 SUV(segment=suv&upcoming=30) | `/vehicles?segment=suv&upcoming=30` | 전체/전체/recent | - | 입찰예정 30일 ✕ | 88 | 1 | 0 | S11-54-enter-segment-suv-M390.png |  칩=['입찰예정 30일 ✕'] 차종활성=['SUV'] 총=88 정렬='recent' |
| M390 | S11-55 | 제조사 [현대] → [적용] | `/vehicles?maker=현대&sort=recent&upcoming=30` | 현대/전체/recent | - | 입찰예정 30일 ✕ | 128 | 1 | 0 | S11-55-apply-segment-suv-M390.png | 미유지 카드에서 온 파라미터 segment=suv&upcoming=30 → 적용 후 URL=/vehicles?judgment=&mak |
| M390 | S11-56 | 달력 날짜 링크 탭 (/vehicles?date=2026-09-01&sort=sale_ | `/vehicles?date=2026-09-01&sort=sale_date` | 전체/전체/sale_date | - | 2026-09-01 매각 ✕ | 28 | 1 | 0 | S11-56-enter-date-M390.png |  칩=['event2026-09-01 매각 ✕'] 총=28 |
| M390 | S11-57 | 정렬 [짧은 주행거리순] → [적용] | `/vehicles?sort=mileage` | 전체/전체/mileage | - | - | 1316 | 1 | 0 | S11-57-apply-date-M390.png | 미유지 date 파라미터 소실=True URL=/vehicles?judgment=&maker=&price=&sort=mileage&q |
| M390 | S10-01 | 제조사 [르노삼성] + 가격대 [3,000만~ (245)] + 매각기일순 → [적용] | `/vehicles?maker=르노삼성&price=3000-&sort=sale_date` | 르노삼성/3000-/sale_date | - | 3,000만~ ✕ | 0 | 1(단일) | 0 | S10-01-zero-M390.png |  총=0 empty=True makers중 르노='르노삼성' |
| M390 | S10-02 | [필터 초기화] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S10-02-after-reset-M390.png | 확인 제조사='' 가격대='' 정렬='recent' 총=1316 — 정렬도 함께 초기화됨 |
| M360 | S1-01 | 직접 진입 /vehicles | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-01-list-initial-M360.png |   |
| M360 | S1-02 | 셀렉트 3개 선택(현대 / 1,000~2,000만 (451) / 매각기일순), 적용 안 | `/vehicles` | 현대/1000-2000/sale_date | - | - | 1316 | 1 | 0 | S1-02-selects-set-before-apply-M360.png |   |
| M360 | S1-03 | [적용] | `/vehicles?maker=현대&price=1000-2000&sort=sale_date` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S1-03-after-apply-M360.png |   |
| M360 | S1-04 | 페이지 번호 [2] | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 0 | S1-04-page2-M360.png |   |
| M360 | S1-05 | #appscroll 절반 스크롤(scrollTop=2237) | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2237 | S1-05-page2-scrolled-M360.png |   |
| M360 | S1-06 | 하단 탭 [calendar_month 경매달력] | `/calendar` | - | - | - | - | - | 0 | S1-06-at-경매 달력-M360.png |   |
| M360 | S1-07 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-07-back-from-경매 달력-M360.png | 미유지 경매 달력→차량목록 탭 복귀:  |
| M360 | S1-08 | 하단 탭 [home 홈] | `/` | - | - | - | - | - | 0 | S1-08-at-대시보드-M360.png |   |
| M360 | S1-09 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-09-back-from-대시보드-M360.png | 미유지 대시보드→차량목록 탭 복귀:  |
| M360 | S1-10 | 하단 탭 [star 즐겨찾기] | `/watchlist?ids=&sort=sale_date` | - | - | - | - | - | 0 | S1-10-at-즐겨찾기-M360.png |   |
| M360 | S1-11 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-11-back-from-즐겨찾기-M360.png | 미유지 즐겨찾기→차량목록 탭 복귀:  |
| M360 | S4-12 | 검색창 '쏘나타' → [적용] | `/vehicles?sort=recent쏘나타` | 전체/전체/recent | 쏘나타 | - | 20 | 1 | 0 | S4-12-q-sonata-M360.png | 유지 검색어='쏘나타' 총=20 칩=[] input.type=text / 검색어 해제 칩 존재=False |
| M360 | S4-13 | 가격대 1,000~2,000만 (9) 추가 → [적용] | `/vehicles?price=1000-2000&sort=recent쏘나타` | 전체/1000-2000/recent | 쏘나타 | 1,000~2,000만 ✕ | 9 | 1(단일) | 0 | S4-13-q-plus-price-M360.png | 유지 검색어='쏘나타' 가격대='1000-2000' 총=9 칩=['1,000~2,000만 ✕'] |
| M360 | S4-14 | 가격대 해제 칩 [✕] | `/vehicles?q=쏘나타&sort=recent` | 전체/전체/recent | 쏘나타 | - | 20 | 1 | 0 | S4-14-price-chip-removed-M360.png | 유지 검색어='쏘나타' 가격대='' 총=20 |
| M360 | S4-15 | 검색창 비우고 [적용] | `/vehicles?sort=recent` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S4-15-q-cleared-apply-M360.png | 유지 검색어='' 총=1316 (검색어만 지우는 ✕ 없음 → 비우고 적용이 유일 경로) |
| M360 | S7-16 | 초기 화면 — [적용] 위치 | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S7-16-initial-applybox-M360.png |  applyBox={'top': 181, 'bottom': 223, 'vh': 780} firstCardTop=0 |
| M360 | S7-17 | 제조사 [기아] 선택만(적용 안 함) | `/vehicles` | 기아/전체/recent | - | - | 1316 | 1 | 0 | S7-17-select-changed-no-apply-M360.png |  applyBox={'top': 181, 'bottom': 223, 'vh': 780} total=1316 (변경 알림/자동제출 |
| M360 | S7-18 | 적용 없이 하단 탭 [calendar_month 경매달력] | `/calendar` | - | - | - | - | - | 0 | S7-18-left-to-calendar-M360.png |  dialogs=[] |
| M360 | S7-19 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S7-19-back-to-list-M360.png | 미유지 제조사='' — 적용 안 한 변경 (알림 없이) 사라짐 |
| D1440 | S1-01 | 직접 진입 /vehicles | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-01-list-initial-D1440.png |   |
| D1440 | S1-02 | 셀렉트 3개 선택(현대 / 1,000~2,000만 (451) / 매각기일순), 적용 안 | `/vehicles` | 현대/1000-2000/sale_date | - | - | 1316 | 1 | 0 | S1-02-selects-set-before-apply-D1440.png |   |
| D1440 | S1-03 | [적용] | `/vehicles?maker=현대&price=1000-2000&sort=sale_date` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 1 | 0 | S1-03-after-apply-D1440.png |   |
| D1440 | S1-04 | 페이지 번호 [2] | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 0 | S1-04-page2-D1440.png |   |
| D1440 | S1-05 | #appscroll 절반 스크롤(scrollTop=2227) | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S1-05-page2-scrolled-D1440.png |   |
| D1440 | S1-06 | 하단 탭 [calendar_month 경매달력] | `/calendar` | - | - | - | - | - | 0 | S1-06-at-경매 달력-D1440.png |   |
| D1440 | S1-07 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-07-back-from-경매 달력-D1440.png | 미유지 경매 달력→차량목록 탭 복귀:  |
| D1440 | S1-08 | 하단 탭 [home 홈] | `/` | - | - | - | - | - | 0 | S1-08-at-대시보드-D1440.png |   |
| D1440 | S1-09 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-09-back-from-대시보드-D1440.png | 미유지 대시보드→차량목록 탭 복귀:  |
| D1440 | S1-10 | 하단 탭 [star 즐겨찾기] | `/watchlist?ids=&sort=sale_date` | - | - | - | - | - | 0 | S1-10-at-즐겨찾기-D1440.png |   |
| D1440 | S1-11 | 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S1-11-back-from-즐겨찾기-D1440.png | 미유지 즐겨찾기→차량목록 탭 복귀:  |
| D1440 | S3-12 | 필터+2페이지+스크롤(2227) 준비 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S3-12-state-page2-scrolled-D1440.png |   |
| D1440 | S3-13 | 화면에 보이는 카드(#19) 탭 | `/vehicle/2025타경10074_1` | - | - | - | - | - | 0 | S3-13-detail-D1440.png |   |
| D1440 | S3-14 | 상세 [뒤로] 버튼 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S3-14-detail-backbtn-D1440.png | 유지 상세 뒤로버튼:  |
| D1440 | S3-15 | 같은 카드(#19) 탭 | `/vehicle/2025타경10074_1` | - | - | - | - | - | 0 | S3-15-detail-again-D1440.png |   |
| D1440 | S3-16 | 상세에서 하단 탭 [directions_car 차량목록] | `/vehicles` | 전체/전체/recent | - | - | 1316 | 1 | 0 | S3-16-detail-tab-vehicles-D1440.png | 미유지 상세→차량목록 탭:  |
| D1440 | S9-17 | 필터+2페이지+스크롤(2227) 준비 | `/vehicles?maker=현대&sort=sale_date&price=1000-2000&page=2` | 현대/1000-2000/sale_date | - | 1,000~2,000만 ✕ | 159 | 2 | 2227 | S9-17-state-page2-scrolled-D1440.png |  바깥 URL=https://naechaget.co.kr/static/frame.html#/vehicles / iframe UR |
| D1440 | S9-18 | 새로고침(F5) | `-` | (프레임 분리) | - | - | - | - | - | S9-18-after-F5-D1440.png | 미유지 바깥 URL=https://naechaget.co.kr/static/frame.html#/vehicles → iframe=No |
| D1440 | S9-19 | 예외(스크립트)  Frame.select_option: Frame was detac | `-` | (프레임 분리) | - | - | - | - | - | S9-19-EXC-D1440.png | 오류  |
### 시나리오별 판정 요약
| 시나리오 | 컨텍스트 | 결과 | 근거 |
|---|---|---|---|
| S1 내비 왕복(달력·홈·즐겨찾기 → `차량목록` 탭) | M390·M360·D1440 | **미유지 ×9** — 전부 초기값(`/vehicles`, 1,316건, recent, 1페이지, scrollTop 0) | S1-07/09/11 ×3 |
| S2 달력 → 브라우저 back | M390 | **유지** — 필터·2페이지·스크롤 2227 | S2-14 |
| S2 상세 → 상세 [뒤로] | M390 | 스크립트 실패(S2-15) → S3 로 검증, 유지 | S3-18 |
| S3 상세 [뒤로] | M390·D1440 | **유지** | S3-18, S3-14 |
| S3 상세 → `차량목록` 탭 | M390·D1440 | **미유지** | S3-20, S3-16 |
| S4 검색어 | M390·M360 | 검색어 유지·조합 유지·가격대만 해제 가능. **검색어 해제 칩 없음**, type=text | S4-12~15(M360) |
| S5 검색 저장 왕복 | M390 | **유지** — 라벨·159=159·필터 동일 | S5-26~28 |
| S6 퀵 칩 토글 | M390 | 다른 필터 **유지**(159→51→159, →75→159). 2페이지에서 토글 → 1페이지(타당) | S6-30~35 |
| S7 적용 버튼 인지 | M390·M360 | 미적용 변경은 **알림 없이 소실**. [적용] top 181–223 → 첫 화면 안 | S7-36~39, S7-16~19 |
| S8 큰글씨 | M390 | 접힌 머리 `검색 · 필터` 만(활성 필터 안 보임). 적용 후 재접힘. 달력 왕복 → 필터 소실 | S8-41~46 |
| S9 PC 프레임 F5 | D1440 | **미유지** — 바깥 해시 고정 → F5 후 첫 경로. 바깥 back 미검증 | S9-17→18, S9b |
| S10 0건 → 초기화 | M390 | 0건·`필터 초기화` 노출 → 전체(1,316) — **정렬도 초기화** | S10-01~02 |
| S11 홈 진입 경로 | M390 | picks·bucket **유지**, segment·date **소실** | S11-50~57 |

## 3. [기능상 불편 목록] — [설계]=코드 의도(지시서 ①~⑤), [버그]=의도와 다름
**U1. [설계 ①] 탭 `차량목록`이 필터·페이지·스크롤을 전부 버린다 — 가장 불편**
- 재현: `/vehicles` → 현대·1,000~2,000만·매각기일순 → [적용] → [2] → 절반 스크롤 → 탭 `경매달력` → 탭 `차량목록`.
- 기대: 159건·2페이지·스크롤 위치 복귀. 실제: 전체 1,316건·recent·1페이지·0. 홈·즐겨찾기·상세에서도 같다. 복귀 화면은 첫 진입과 **md5 동일**(`S1-01-list-initial-M390.png` = `S1-07…` = `S1-09…` = `S1-11…` = `S3-20…` = `S7-39…`).
- 근거: S1-07/09/11 ×3컨텍스트, S3-20, S8-45. 코드: `base.html` `tab('/vehicles',…)`/`navitem('/vehicles',…)` 쿼리 없음. 반면 `web/app.py` 는 `/vehicles` 응답마다 `set_cookie("last_list", _cur_url(request))` 하고 상세 [뒤로] href 가 그 값을 쓴다(S3-17 backHref).
- 영향(추정): 목록↔달력·홈을 오가는 모든 사용자, 왕복마다. 설계상 그렇다고 병기 — 그러나 재료(쿠키·`nc:scroll`)는 이미 있다.

**U2. [버그] [적용]이 `segment`·`date`(·`court`)를 버린다 — 다른 진입 파라미터와 비일관**
- A: 차종 카드 SUV(`segment=suv&upcoming=30`, 88건, SUV 칩 활성) → 제조사 현대 → [적용] → `upcoming=30`만 남고 128건, 차종 `전체`. B: 달력 날짜(`date=2026-09-01&sort=sale_date`, 28건) → 정렬 변경 → [적용] → `/vehicles?sort=mileage` 1,316건, 날짜 칩 소멸.
- 근거: S11-54→55, S11-56→57. 코드: 폼 hidden 은 `upcoming/result/status/cond/bucket/usepick/picks`만 — `segment/date/court/promising` 없음(`vehicles.html`). 같은 조작에서 `picks=1`·`bucket=lowconf`는 유지(S11-51/53)로 대조.
- 영향(추정): 대시보드 차종 카드 5개·달력 날짜·법원 선택에서 온 뒤 셀렉트를 바꾸는 사용자 — **모수가 조용히 바뀐다**(템플릿 주석이 bucket 에 대해 경고한 그 현상).

**U3. [버그] 활성 칩이 좁은 폭에서 줄바꿈** — 390px 에서 `입찰예정 30일 ✕` 2줄, `2026-09-01 매각 ✕` **3줄**. 비활성 칩·가격대 칩은 `whitespace-nowrap shrink-0`이 있는데 활성 `upcoming/date/court/result/cond` 칩에는 없다. 근거: S11-54, S11-55, S6-30, S11-56.

**U4. [설계+버그 경계] PC 프레임: F5 하면 첫 경로로 회귀** — iframe 이 `…page=2`까지 가도 바깥은 `frame.html#/vehicles`(S9b-02/03 두 번 이동에도 불변). F5 → iframe `/vehicles` 전체(S9-17→S9-18). `frame.html`은 최초 해시만 읽어 `iframe.src`에 넣고 이후 갱신 없음. 바깥 back: 미검증(S9b-04).

**U5. [설계] `매각기일순`이 이미 끝난 물건부터** — 현대·1,000~2,000만·매각기일순 1페이지 첫 카드 `매각 종료 · 2026-08-18 낙찰 13,150,000`, 2페이지 `2026-08-25/26 매각 종료`. `입찰예정 30일만`을 켜면 159→51. 대시보드 링크는 전부 `upcoming=…&sort=sale_date`로 짝을 지어 이 문제를 피한다(`dashboard.html`) — 셀렉트로 직접 고른 사용자만 맨 앞에서 끝난 경매를 만난다. 근거: S1-03, S1-05, S6-30.

**U6. [설계 ④] 셀렉트만 바꾸고 떠나면 변경이 조용히 사라진다** — 기아 선택 → 달력 → 목록 → `전체 제조사`, 알림 없음(dialogs=[]), 자동 제출 없음. 완화: [적용]이 top 181–223(844/780 뷰포트)로 첫 화면 안, 셀렉트 바로 옆(S7-36, S7-16).

**U7. [설계] 검색어를 지우는 손잡이가 없다** — 검색어 칩 없음, `input.type=text`라 브라우저 ✕도 없음. 비우고 [적용]이 유일(S4-14→15).

**U8. [설계] 큰글씨 모드 접힌 필터 머리가 활성 필터를 말하지 않는다** — `검색 · 필터`만, `총 159건`은 보이는데 무엇으로 걸렀는지는 펼쳐야 안다(S8-41).

**U9. [설계] `필터 초기화`가 정렬까지 되돌린다** — `href="/vehicles"`라 매각기일순 → 최근 등록순(S10-02). 낮은 우선순위.

## 4. [점수·지적 5건] — app-qa-auditor 총점 81/100 (첫 회차 — 검색·필터 상태 유지 워크스루 기준)
| 항목 | 점수 | 근거 |
|---|---|---|
| 데이터 무결성 | 27/30 | 같은 조건 수치가 어디서나 일치: 가격대 옵션 `(159)` = `총 159건` = 검색 저장 baseline 159 = `/api/vehicles/count` 159(S1-03, S5-26~28). 0건은 옵션 `3,000만~ (0)`·빈 상태로 정직(S10-01). −3: 상세·리포트 수치는 이번 범위 밖(미검증). |
| 응답·안정성 | 18/20 | 문서 로드 149·API 117 중 4xx/5xx **0건**. M360 20로드 47초(대기 40초 포함) → 로드당 ≈0.35초. back_forward 복원 정상. −2: 잘못된 파라미터·없는 물건은 이번 범위 밖. |
| 크로스플랫폼·예외 | 15/25 | 360·390·1440 가로 스크롤 없음(`docScrollX=false`). −4 활성 칩 2~3줄 줄바꿈(U3), −3 [적용]이 segment/date 를 버려 모수 변경(U2), −2 PC 프레임 F5 소실(U4), −1 큰글씨 접힌 머리 무표시(U8). |
| 보안·개인정보 | 21/25 | 검색 저장은 `localStorage naechaget:searches`만(S5-26 실측), 서버 전송 없음. `last_list` 쿠키는 목록 URL만, `secure; samesite=lax`(코드). −4: 응답 헤더·노출 토큰 재검사는 이번 회차에 안 함(미검증, 결함 아님). |

**지적 1. 탭 `차량목록` 복귀 시 필터·페이지·스크롤 전부 소실 (U1)** — 현재: 세 컨텍스트 12회 전부 `/vehicles` 전체 1,316건·1페이지·0. 목표: 탭이 **마지막으로 본 목록 URL**로 간다(서버 `last_list` 쿠키 또는 sessionStorage — 상세 [뒤로]가 이미 같은 값을 쓴다). 스크롤은 `nc:scroll`이 URL별로 있으니 복원 조건을 `back_forward` 외 "탭 복귀"에도 연다. 새로 시작하려는 사용자를 위해 목록 안 `필터 초기화`는 그대로. 근거: S1-07/09/11-{M390,M360,D1440}, S3-20-M390, S8-45-M390.

**지적 2. [적용]이 `segment`·`date`·`court` 파라미터를 버린다 (U2)** — 목표: `bucket`과 같은 방식으로 `segment`·`date`·`court`(·`promising`) hidden input, 또는 [적용]이 현재 URL의 필터 파라미터를 병합 제출. 적용 후 칩이 남아야 한다. 근거: S11-54→55, S11-56→57.

**지적 3. 활성 칩 `입찰예정 30일 ✕`·`2026-09-01 매각 ✕` 줄바꿈 (U3)** — 목표: 활성 칩 전부에 비활성 칩·가격대 칩과 같은 `whitespace-nowrap shrink-0`; 320·360·390에서 pill 높이 = 이웃 높이 확인. 근거: S11-54, S11-55, S11-56, S6-30.

**지적 4. PC 프레임 F5 → 첫 경로 회귀, 바깥 해시 미갱신 (U4)** — 목표: iframe `load`에서 `contentWindow.location.pathname+search`(같은 출처)를 읽어 바깥 `location.hash`를 `replaceState`로 갱신 → F5 후 마지막 경로로 열림. 바깥 back 은 갱신 뒤 재측정. 근거: S9-17→S9-18, S9b-02/03.

**지적 5. `매각기일순`이 끝난 경매부터 나열 (U5)** — 목표: `매각기일순`을 "오늘 이후 가까운 순 → 그 뒤 지난 기일"로, 또는 라벨을 정직하게(`매각기일 오름차순(지난 기일 포함)`), 또는 대시보드처럼 `upcoming`과 짝. 순서·라벨 문제, 데이터 변경 아님. 근거: S1-03, S1-05, S6-30.

**확인 필요(추측)**: 바깥 브라우저 back 이 iframe 이동을 되감는지(S9b-04) · 오프캔버스 사이드바가 접근성 트리에 남는지 · 큰글씨 사용자가 접힌 `검색 · 필터` 머리를 필터로 인지하는지.

**잘하고 있는 것**: ① 상세 [뒤로]·브라우저 back 이 필터·2페이지·스크롤 2227px 까지 복원(S3-18, S2-14, S3-14) ② 가격대 옵션 라벨에 현재 필터 기준 건수(`1,000~2,000만 (159)`, `3,000만~ (0)`), 0건 빈 상태 문구·`필터 초기화` 명확 ③ 검색 저장 → 즐겨찾기 카드 → 복귀가 라벨·건수·필터 모두 일치(S5-26~28), 검색어와 가격대 해제 칩이 서로를 지우지 않음(S4-13~14).

## 5. [측정 조건]
- 대상: 라이브 비로그인 공개 뷰. 라이브 배포 `3c64dd7`(20:17) · 로컬 HEAD `6704728`(docs 커밋만 추가). 화면에 가격대 셀렉트(FEAT-1)가 렌더되므로 3c64dd7 이상임을 간접 확인.
- 도구: Playwright(Python) Chromium 148 헤드리스. 각각 새 컨텍스트 — M390: 390×844, `is_mobile=True, has_touch=True`, ko-KR, DPR 2, Android Chrome UA · M360: 360×780, 같은 옵션 · D1440: 1440×900, 마우스 기본, DPR 1 — `/vehicles` 진입 시 `base.html`이 `/static/frame.html#/vehicles`로 `location.replace`, 이후 `#f` iframe(420px 폭) 안에서 조작.
- 페이스: 이동마다 `load` + 2초 대기. 20:34:32–20:50:19 KST. 문서 로드 합계 **149**(상한 150; 실패한 첫 실행 30 포함). API 117회. 4xx/5xx 0건 → 중단 조건 미발동.
- 스크린샷 98장, md5 중복 17그룹 — 모두 **같은 화면**(첫 진입 = 탭 복귀 화면 등). 그룹 목록은 `HEAD.txt` 하단.
- 한계: S2 후반 스크립트 타임아웃 → S3 로 대체. S9 바깥 back 미검증. M390 S4 검색어 열 측정 오류 → URL·M360 재측정으로 확인.

## 6. 확인된 사실 / 추정
- **확인된 사실**: §2 표의 모든 값(DOM 읽기·스크린샷), 지적 1~5의 현재 상태, md5 중복 사유, 로드·오류 수치, 코드 인용(hidden 목록·`last_list`·`frame.html`). Steward 재현 항목은 머리말 참조.
- **추정**: 영향 범위는 사용 로그 없이 흐름 구조에서 추정. 지적 5의 "108건은 30일 안 매각이 아니다"는 159−51 계산값. S9b-04 바깥 back 은 미검증.
