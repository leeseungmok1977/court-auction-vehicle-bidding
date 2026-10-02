---
order: 2026-10-02-03
from: frontend-engineer
ticket: MKT-1
result: done
verified: 재현
handoff: []
---

# MKT-1 판정 원칙 노출 — 랜딩 블록과 base 한 문장 (frontend-engineer, 지시서 2026-10-02-03)

> Steward 옮김(2026-10-02 09:30): 담당은 reports/ 에 쓰지 못해 본문을 인계 메시지로 보냈다. 요지·수치 그대로.
> 기준 HEAD 9c3374c(지시서의 09ca281 위 문서 커밋 1개 — web·tests·src diff 0), 작업 중(08:09~09:2x) 이동 없음. 커밋·push·배포·ssh·외부 요청 0, 서버 코드 무수정, data/·8765 무접촉.

## [요약]
- **랜딩**: '핵심 가치' 섹션 안, 3카드 그리드(셋째 '안전한 산정 로직') 바로 뒤 — 섹션의 마지막 요소. 확정 문구(제목·보조줄·항목 4) 글자 그대로, 상자 없음(테두리·면·그림자 0 — 가벼운 체크리스트).
- **base.html**: 같은 한 문장 두 자리 — 사이드바('참고용 분석 도구(투자 권유 아님)' 바로 뒤), 모바일 푸터('…입찰할 수 없습니다.' 바로 다음 줄).
- **app.css**: 새 유틸리티 없음, `npm run build:css` → d1109243 그대로(편집마다 4회 — 주석 낱말 영향 없음, TEST-4). **배포 단위: 템플릿 2 + 새 테스트 1.**
- 테스트: 새 파일 18노드 — HEAD 코드에서 17 빨강·대조군 1 초록, 작업 트리 18 통과, 템플릿 변이 21/21. 전체 스위트 **2,996 passed · 5 xfailed · 0 failed**(노드 2,983 → 3,001, 네트워크 0).
- 전수 렌더 대조(4,841쪽): 바뀐 쪽은 랜딩·about 과 base 를 쓰는 화면(상세·목록·홈·달력·적중률·관심)뿐, 세 조각(블록·사이드바 문장·푸터 줄)을 지우면 모든 쪽 md5 같음, 리포트·개인정보처리방침 바이트 같음.
- **스토어 `06_landing` 은 이 블록을 담지 않는다** — 540×960 첫 화면만 찍는데 블록은 1657px 에서 시작(같은 조건 전후 md5 같음 e33c4fbd).

## 바꾼 파일
| 파일 | 전 | 후 |
|---|---|---|
| web/templates/landing.html (CRLF) | 4dbc03af | 9305a637 |
| web/templates/base.html (CRLF) | f2ea92d5 | ff6b69cc |
| tests/test_mkt1_principles.py (LF) | — | 03d70581(새) |
| web/static/app.css | d1109243 | 같음 |

## 자리별 (요지)
- **랜딩 블록** `<div class="pt-10 max-w-2xl mx-auto">`: 카드와 40px, 폭은 섹션 머리말과 같은 2xl. 제목 h3 20px·600·딥네이비 가운데(카드 제목 18px 과 섹션 h2 30~36px 사이), 보조줄 16px `text-mut` 가운데, 항목 14px `text-txt`. 체크 아이콘 `check_circle` `text-primary` `aria-hidden` — 초록을 안 쓴 이유: 이 앱에서 초록 체크는 홈 '지금 입찰 추천' 표시라 '입찰하지 마세요' 옆에서 뜻이 섞인다. 항목 사이 12px, 아이콘 중심과 첫 줄 중심 차이 보통 1px·큰글씨 2px. 화면 낱말 `"입찰하지 마세요"`·`'판정 보류'` 를 `whitespace-nowrap` 으로 묶음(360px '판정 / 보류', 390px '입찰하지 / 마세요' 갈림을 캡처로 확인 뒤 — 글자 그대로, 태그만). Jinja 주석: 근거 함수(use_accident_rate·accident_evidence / estimate_withheld / floor_unconfirmed·refresh_lagged_floors / bid_state lowconf)·상자 없는 이유·초록 안 쓴 이유(한글·함수명만). 대비: 항목 14.73 · 보조줄 5.02 · 아이콘(장식) 5.86.
- **base 한 문장**: 사이드바 `…(투자 권유 아님)<br><span class="inline-block" style="text-wrap:pretty">문장</span>`, 모바일 푸터 기존 줄 다음 `<span class="w-full text-[11px]" style="text-wrap:pretty">문장</span>`(같은 11px·mut). text-wrap:pretty — 넣기 전 사이드바 1024·1440(보통·큰글씨)과 큰글씨 푸터 360·390 에서 '계산합니다.' 한 낱말만 다음 줄, 넣은 뒤 모두 '…사고차로 / 가정해 계산합니다.'(이 앱의 기존 인라인 text-wrap 방식). 대비 사이드바 5.30 · 푸터 5.02.

## 테스트 · 렌더 대조 · 캡처 (요지)
- `tests/test_mkt1_principles.py` 18노드: 문구 글자·순서(공개·관리자) 2 · 위치(섹션 안·셋째 카드 그리드 바로 뒤·섹션 마지막·정직 배너 앞) 1 · 상자 아님·아이콘 장식·초록 아님·숨김 아님 1 · base 두 자리(화면 6 × 공개·관리자 — 2번·앵커 바로 뒤·숨기지 않음) 12 · 과장 낱말 0(새 문구에 걸러·안전합니다·보장·완벽·확실·무조건·100%·절대·손실을 막, 랜딩 전체에 앞의 셋) 1 · 대조군(앵커) 1. 변이 21(블록 위치 · 문구 한 글자×3·순서·빠짐·h3→h4 · 상자·아이콘 초록·aria·과장 낱말 · 사이드바·푸터 빠짐·앵커 앞·관리자 전용·한 글자 · 숨김×3) 모두 잡힘. 스위트 사본(9c3374c 아카이브 + 작업 트리 + ALT_TEXT), `-p netguard`, 08:50:47~09:16:02.
- 렌더 대조(10-01 사본 c3a96d28, 10-01 13:40 고정): 4,841쪽(상세 공개·관리자 1,587×2 · 리포트 1,587 · URL 24×2 · 관심 32묶음) — 다른 쪽 3,252(상세 3,174 + URL 46 + 관심 32), 같은 쪽 리포트 1,587 + privacy 2, 가림 뒤 md5 ≠ 0, 규칙 위반 0, 200 → 200.
- 캡처 `screenshots/mkt1/`(before·after 각 12장 — 랜딩 블록 6폭 + 큰글씨 320, 사이드바 1440, 모바일 푸터 390·320 + 큰글씨 320·390, HEAD.txt e1ca12d9): 12쌍 모두 md5 다름, 24장 Read. 넘침 0·화면 밖 0. 블록 높이 320 419px / 768·1440 258px / 큰글씨 320 701px, 항목 줄 수 320 [2,2,3,2] · 1440 [1,1,1,1] · 큰글씨 320 [3,4,4,3]. 큰글씨 320 은 html 125% 주입으로 흉내(랜딩은 앱 토글을 읽지 않음 — 발견 4). 사이드바는 screen.width 800 으로 폰 프레임 분기를 끄고 촬영.

## 발견 · 판단 거리 (담당 문장 요지)
1. **[기존 결함, 범위 밖] 아이콘 크기 클래스가 전부 무시된다** — `tailwind_input.css` 의 `.material-symbols-outlined{font-size:24px}` 가 `@tailwind utilities` 뒤(레이어 밖)라 특이도가 같아 text-sm·lg·3xl·[13px]…를 이긴다. HEAD 실측 홈 48·랜딩 14·목록 56개 아이콘이 모두 24px(예: 랜딩 머리 gavel text-3xl 의도 30px, 정직 배너 balance text-4xl 36px, 하단 탭 text-[26px] — 모두 24px). 고치면 앱 전체 아이콘 크기가 바뀌어 별도 티켓·전 화면 검수 필요.
2. [판단 거리] 체크 아이콘 색 — DESIGN.md 는 primary 를 CTA·링크 전용으로 둔다, 같은 섹션 카드 아이콘 타일(이미 text-primary)과 맞췄다. 대안 text-mut. 아이콘(24px)·글자(14px) 비율도 함께.
3. 사이드바는 공개 데스크톱 브라우저에 안 보인다(base.html 머리 스크립트가 공개 데스크톱을 폰 프레임 420px 로 보냄 — 그 사용자는 모바일 푸터 문장을 본다). 사이드바 문장은 설치형 데스크톱 앱·관리자만.
4. 랜딩은 앱 '큰글씨' 토글을 읽지 않는다(base.html 미상속 — 실측 토글 켜도 L320 root 16px). 기존 동작.
5. 사이드바 세로 여유: 1024×560 큰글씨·관리자에서 메뉴 마지막 항목과 푸터 사이 0(넘침 0), 공개 최소 42px.
6. **기존 문구**: 바로 위 셋째 카드 '…자동 경고(입찰 중단 기준)로 **손실을 막습니다**'는 새 블록의 과장 기준('손실을 막')에 걸리는 결과 약속. 큰글씨 390 모바일 푸터 기존 줄 '…입찰할 수 / 없습니다.' 외톨이.
7. **항목 4 문구 경계**: 표본 부족·신뢰도 낮음·중앙값 없음은 lowconf '시세 신뢰도 낮음 — 판정 보류'라 참, 동급 시세가 아예 없는 물건(nomarket)은 '동급 시세 없음' 표시 — '판정 보류' 낱말은 아니지만 추천에서 빠지는 것은 같다.
8. 작업 중 다른 손의 변경(docs/backlog.md · reports/ 새 파일 3 · data/ 순환계·8765 파일)은 담당 것이 아님.

> **Steward 판정(09:35)**: 발견 6 → 셋째 카드 문구를 사실로("…사고·침수 이력이 있으면 입찰 중단 기준으로 자동 경고합니다.") · 기존 푸터 줄에도 같은 text-wrap. 발견 7 → 항목 4 를 "비교할 시세가 부족하거나 믿기 어려우면 판정을 보류하고 추천에 넣지 않습니다."(따옴표 낱말을 빼 nomarket 도 참이 되게 — Play 설명 같은 줄도 함께). 발견 1 → DES-8 티켓. 발견 2 → app-design 검수에 묻는다. 발견 4 → DES-9 티켓(작은 일).

## 추가 — 2회차 문구 손질 3건 (Steward 확정, 09:24~09:56)
- ① 셋째 카드 `…<b class="text-txt">사고·침수 이력이 있으면 입찰 중단 기준으로 자동 경고</b>합니다.`(랜딩 전체 '손실을 막' 0 — 테스트 고정) ② 넷째 항목 `비교할 시세가 부족하거나 믿기 어려우면 판정을 보류하고 추천에 넣지 않습니다.`(nowrap 정리, 근거: lifecycle 에서 nomarket·lowconf 는 각자 칸 — 둘 다 review·usepick 밖) ③ 푸터 기존 줄 `style="text-wrap:pretty"`(큰글씨 390 '…입찰할 수 / 없습니다.' → '…입찰할 / 수 없습니다.', 목록 큰글씨 390 같음, 다른 폭 그대로). 주석 새 내용으로(규칙 8).
- md5: landing 9305a637 → **339d4498** · base ff6b69cc → **7b5b65fa** · test_mkt1_principles 03d70581 → **e4065ff5**(18 → 20노드) · app.css d1109243 그대로. 배포 단위 템플릿 2 + 테스트 1.
- 테스트: HEAD 9c3374c 템플릿 19 failed · 1 passed(대조군) / 1회차 트리 5 failed(넷째 항목 ×2 · '손실을 막' · 셋째 카드 본문 · 푸터 pretty) / 후 20 passed. 새 테스트 `test_third_card_says_what_it_does_not_a_promise` · `test_footer_and_sidebar_lines_do_not_strand_the_last_word`, 과장 낱말 검사를 랜딩 전체로(9개 — '확실'은 정직 배너 '불확실성' 제외). 변이 30/30. 전체 스위트 **2,998 passed · 5 xfailed · 0 failed · 0 skipped**(09:31:32~09:55:20).
- 렌더 대조(1회차 끝 ↔ 손질 뒤, 10-01 사본): 4,841쪽 중 3,252 다름, 가림 뒤 ≠ 0, 조각 개수 규칙 위반 0, 200 → 200. 캡처 `screenshots/mkt1/after2/`(5쌍 — 랜딩 카드3+블록 390·320·1440·LE320, 홈 푸터 L390, HEAD.txt d590f7d5) 모두 다름·Read. 측정 넘침 0·화면 밖 0.
- 발견: 셋째 카드 마지막 줄이 768(3열)·큰글씨 320 에서 '경고합니다.' 한 낱말(전엔 '손실을 막습니다.' 두 낱말) — 5음절이라 짧은 꼬리는 아니라 보고 둠.
- **Steward 재현(10:00)**: md5 4개 일치, `test_mkt1_principles`·`test_rec15_frontend`·`test_rec13_frontend` 55 passed, `after2/after/landing-card3block-N390` Read — 카드 새 문장·블록 제목·보조줄·체크 항목 4 확인.

## 추가 — 3회차: app-design 검수 반영 (10:08~11:01)
- ① 제목 `모르는 건 <span class="whitespace-nowrap">안전한 쪽으로</span> 계산합니다`(h3 하우스 balance 그대로) — 큰글씨 흉내 320·360 '모르는 건 안전한 / 쪽으로…' → '모르는 건 / 안전한 쪽으로 계산합니다', 측정한 모든 폭에서 '안전한' 뒤 줄바꿈 0 ② 체크 아이콘 4개 `text-primary` → `text-mut`(rgb 83,58,253 → 94,108,133, 24px 그대로, 그래픽 대비 5.02) ③ 셋째 카드 굵은 글씨 안 `…기준으로 <span class="whitespace-nowrap">자동 경고</span></b>합니다.`(카드 p 는 이미 계산값 pretty — 묶음으로 768·큰글씨 320 갈림 0, 마지막 줄 '자동 경고합니다.', 다른 두 카드 렌더 바이트 같음) · 푸터 기존 줄 `…이 앱에서는 <span class="whitespace-nowrap">입찰할 수 없습니다.</span>`(큰글씨 390·360 '…이 앱에서는 / 입찰할 수 없습니다.').
- md5: landing 339d4498 → **5de29e45** · base 7b5b65fa → **eda98274** · test_mkt1_principles e4065ff5 → **c902f73b**(21노드) · app.css d1109243(재빌드 ×5 같음).
- 테스트: HEAD 20 failed · 1 passed(대조군) / 2회차 트리 4 failed(아이콘 색·제목·카드·푸터 묶음) / 후 21 passed, 변이 36/36. 전체 스위트 1차 2 failed(`test_ux9_bfcache_list::test_skeleton_still_shows_on_slow_network` · `test_ux9_qa_adversarial::test_offline_error_page_then_back` — CPU 부하 중 타이밍, 단독 3회 통과) → 깨끗한 사본 **2,999 passed · 5 xfailed · 0 failed**(10:47~11:00, 노드 3,004).
- 렌더 대조(2회차 ↔ 3회차, 4,841쪽): 네 자리를 가리면 다른 쪽 0, 조각 개수 위반 0. 캡처 `after3/`(HEAD.txt 38981174): title-LE320 9b02da31 → 6e49d4b1 · title-N320·N360 같음(기대대로 — 전후 한 줄) · block-N390 c014733c → 7cfdc450(아이콘 색만) · card3-LE320 4ab67280 → 0a583c5f · home-foot-L390 639119d3 → 862f8c23, 12장 Read, 넘침 0.
- 발견: ux9 bfcache·느린 회선 브라우저 테스트 2개가 CPU 부하에서 실패(무관 — TEST-5 계열 '타이밍'), 큰글씨 320 제목 두 줄 길이 불균형은 검수 목표가 허용한 모양.
- **Steward 재현(11:10)**: md5 일치, 관련 3파일 56 passed, `after3/after/landing-title-LE320`·`landing-block-N390` Read — 제목 '모르는 건 / 안전한 쪽으로 계산합니다', 체크 아이콘 회색.
