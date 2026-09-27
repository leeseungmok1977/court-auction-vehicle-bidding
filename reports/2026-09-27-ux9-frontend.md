---
order: 2026-09-27-62
from: frontend-engineer
ticket: UX-9
result: done
verified: 재현
handoff: []
---
# UX-9 폰 뒤로가기 목록 사라짐·스크롤 위치 손실 수정 (2026-09-27-62 / frontend-engineer)

- **기준 커밋:** 작업은 `a255a7c` 에서 시작했다. 작업 중 HEAD 가 `5602e91` 로 움직였는데 문서만 바뀌었다(backlog.md·reports 2건). `git diff a255a7c 5602e91 -- web/ src/ tests/` 는 비어 있다.
- **하지 않은 것:** 커밋·배포·라이브 요청·운영 DB 쓰기.
- **검증 환경:**
  - DB 는 `data/backups/auction-20260927.db.gz`(md5 3e7d01aa)를 스크래치에 풀어 `sqlite3 backup(mode=ro)` 로 만든 사본이다.
  - 로컬 서버는 127.0.0.1:8791 이고, 느린 망 캡처 때만 :8792 를 썼다. 측정 뒤 둘 다 닫았다.
- **바꾼 파일**
  - `web/templates/vehicles.html`: 스켈레톤 IIFE 하나만 바꿨다(앵커 `var y0=null` · `function undo()`). md5 `6a8436f9`.
  - `tests/test_ux9_bfcache_list.py`: 새 파일, 15건.
- **손대지 않은 파일**
  - `base.html`: md5 `dd36a1c8` 그대로.
  - `web/static/app.css`: `npm run build:css` 를 실행했지만 새 클래스가 없어 md5 `f901bb86` 이 그대로다.
- **보고서 파일:** 하네스 규칙 때문에 reports/ 에는 쓰지 않았다. 이 전문을 `reports/2026-09-27-ux9-frontend.md` 에 저장해 주십시오.

## [요약]
- **N1 고쳤다(확인).** '2'·'다음 ›' → 뒤로 가 bfcache 로 복원되면(pageshow persisted=true) 목록이 보이고 스켈레톤은 숨는다.
  - 390: 누르기 전 4240 → 뒤로 뒤 4240. 변경 전에는 스켈레톤 고착에 313 이었다.
  - 6폭(320~1440) 모두 누른 자리로 정확히 돌아왔다.
- **지적 2 고쳤다(확인).** `nc:scroll` 저장값이 누른 자리가 됐다.
  - bfcache 경로와 새 로드 back_forward 경로(qa 의 4196→154 가 이 경로였다) 둘 다 확인했다.
  - base.html 은 바꾸지 않았다.
  - UX-2 탭 복귀 회귀 테스트와 기존 UX-2 테스트가 모두 초록이다.
- **N2 고쳤다.** 셀렉터를 `#listFilter form` 으로 바꿨다. N1 처방과 같은 회차라 [적용] → 뒤로에서도 고착이 없다(테스트 ③).
- **스켈레톤의 가치는 유지했다.** 느린 망에서 '2' 를 누르면 다음 화면이 올 때까지 스켈레톤이 화면 안에 보인다. 페이지 안 표본 60/60 이 스켈레톤이었고 top 은 230 이다.
- **나쁜 소식:** 복원 직후 스켈레톤 **1프레임**은 완전히 없애지 못했다. 실제 코드로 15회 중 10회, 69~148ms 보였다. 원인과 대안은 §2 에 있다.

## 1. 무엇을 바꿨나 — 스켈레톤 IIFE (vehicles.html)
- `show()`
  - 숨기기 직전에 `y0 = #appscroll.scrollTop` 을 잡는다.
  - 이미 떠 있으면 처음 값을 지킨다([적용]을 두 번 눌러도 줄어든 값으로 덮지 않는다).
- `undo()`: 목록을 보이고, 스켈레톤을 숨기고, `scrollTop = y0` 을 넣는다.
- `window.addEventListener('pagehide', undo, true)`
  - capture 로 거는 이유: base.html 의 pagehide 저장보다 먼저 돌아야, 되돌린 값이 저장된다.
  - visibilitychange 저장은 pagehide 뒤에 오므로 따로 할 일이 없다.
  - 저장 순서는 setItem 계측으로 확인했다(`click` 에서 313 → `pagehide` 에서 3961 → `visibilitychange` 에서 3961).
- `pageshow`(persisted) 에서도 `undo()` 를 부른다. 보험이다.
- 제출 셀렉터: `form[action="/vehicles"]` → `#listFilter form` (N2).
- **지시서 밖 추가 1건.** 수정 키(Ctrl·Meta·Shift·Alt)를 누른 클릭이나 주 버튼이 아닌 클릭에는 스켈레톤을 걸지 않는다.
  - 그런 클릭은 새 탭을 열 뿐이라 이 문서가 떠나지 않고, pagehide 도 오지 않는다. 그러면 원래 탭이 그대로 고착된다.
  - HEAD 에서 데스크톱 Ctrl 클릭으로 재현했다(테스트가 HEAD 에서 빨간불).
  - 같은 고착의 다른 경로라 한 줄로 막았다. 원치 않으면 되돌리기 쉽다.
- **동작 변화 (N2 의 부수 효과).**
  - 데스크톱 헤더 검색 제출은 이제 스켈레톤을 띄우지 않는다. 예전에는 셀렉터가 이 폼을 잘못 잡아서 띄웠다.
  - 필터 [적용] 제출은 이제 폰·데스크톱 모두 스켈레톤을 띄운다.

## 2. 방식 선택 — 무엇이 첫 페인트에 스켈레톤을 덜 보이나 (측정)
**측정 조건**
- Chromium 148(Playwright 1.60), channel=chromium, bfcache 켬.
- 390×844 · 360×780, 공개 뷰(XFF), 운영 사본.
- 뒤로 간 뒤의 컴포지터 프레임을 CDP screencast 로 모두 받았다.
- 프레임 판정: 스켈레톤 기준 프레임과 최종 목록 프레임 가운데 어느 쪽에 더 가까운지로 나눴다.
- 시안 A·B 는 템플릿을 바꾸지 않고 init script 로 주입했다. '실제'는 구현한 코드다.

| 방식 | 스켈레톤 프레임이 보인 회차 | 프레임 수·시간 | 뒤로 뒤 scrollTop (390 기준 4240) |
|---|---|---|---|
| 현행(HEAD) | 전부 | 영구 고착 | 313 |
| A: pageshow(persisted)에서만 되돌림 | 390 10/10 · 360 5/5 | 2~4프레임, 81~334ms | 313 · 377 (틀림) |
| B: pagehide 에서 되돌림(주입) | 390 6/10 · 360 4/5 | 1프레임, 72~125ms | 4240 · 4319 |
| **실제 구현(B + pageshow 보험)** | 390 8/10 · 360 2/5 = **10/15** | **1프레임, 69~148ms** | **4240 · 4319** |

**판단:** B 를 골랐다. 프레임 수가 줄고(2~4 → 1), 시간도 줄고(최대 334 → 148ms), 스크롤이 맞는다.
- A 는 스크롤도 틀린다. 줄어든 값(313)이 이미 저장돼 있어서 base.html 의 pageshow 복원이 화면을 그 값으로 끌어내린다.

**남은 1프레임의 원인 (추정)**
- 떠나기 직전 마지막으로 그린 프레임은 줄어든 위치의 스켈레톤이다. 복원된 페이지가 새 프레임을 낼 때까지 이 프레임이 보인다.
- pagehide 이후에는 페이지 JS 가 그 그림을 바꿀 수 없다.
- 없애려면 떠나기 전에 스켈레톤을 그리지 않아야 한다. 방법은 둘이다.
  - (a) 스켈레톤을 짧게 늦춰 띄운다. 빠른 이동에서는 아예 그려지지 않는다.
  - (b) 목록을 숨기는 대신 보던 자리 위에 겹친다. 그러면 남은 프레임도 제자리에 보인다.
- 둘 다 표시 방식을 바꾸는 일이라 이번 범위에 넣지 않았다. 디자인 자리의 판단이 필요하다.
- 헤드리스 screencast 로만 쟀다. 실기기에서 실제로 보이는지는 미검증이다.

**Chromium 에서 확인한 사실 하나**
- 목록을 다시 보이면 Chromium 은 원래 스크롤 위치를 스스로 되찾는다. pagehide 저장값이 3961 이었다(누르기 전 3961). 지연 0초와 1초 두 조건에서 확인했다.
- 그래서 `scrollTop=y0` 는 Chromium 에서는 없어도 된다. 다른 엔진(WebKit·Gecko)은 확인하지 못해 명시적으로 넣었다. WebKit·Firefox 가 설치돼 있지 않아 미검증이다.

## 3. 테스트 — tests/test_ux9_bfcache_list.py (15건)
**하네스 함정 두 개를 발견했다. 테스트 docstring 에 적었다.**
- ① Playwright 는 `--disable-back-forward-cache` 로 브라우저를 띄운다. `ignore_default_args` 로 이 인자를 뺀다.
- ② **기본 headless(chromium-headless-shell)는 ①을 해도 bfcache 를 쓰지 않는다.**
  - CDP `backForwardCacheNotUsed` 이유: `BackForwardCacheDisabledForDelegate`.
  - `channel="chromium"`(새 headless)이 필요하다. qa 는 channel=chrome 을 써서 이 문제를 피했다.
- 그래서 매 복귀마다 `pageshow` 의 `persisted` 를 단언한다.
- 변이 시험으로 확인했다. channel 을 빼면 6/6 이 persisted 가드에서 실패한다. 공허 통과가 막힌다.

**측정 함정 하나**
- 이동이 걸려 있는 동안에는 `page.evaluate`·`page.screenshot`·CDP `Runtime.evaluate` 가 커밋될 때까지 돌아오지 않는다(실측 3.5~4.4초).
- 그동안 페이지 JS 는 100ms 마다 돈다.
- 그래서 느린 망 테스트는 페이지 안 기록기(sessionStorage)를 쓰고, 캡처는 screencast 프레임을 쓴다.
- 서버 지연은 서버 쪽(SLOW)에서 건다.

**테스트 목록**

| 지시 항목 | 테스트 | 작업 트리 | HEAD |
|---|---|---|---|
| ① '2' → 뒤로 (390·360) | `test_page_link_then_back_restores_list_and_scroll[2-*]` | 통과 | **실패** (results False·skeleton True·top 313/377) |
| ② '다음 ›' → 뒤로 (390·360) | `…[다음-*]` | 통과 | **실패** (같은 증상) |
| ③ [적용] → 뒤로 (390·360) | `test_apply_then_back_restores_list` | 통과 | 실패 (N2: 스켈레톤이 필터 폼에 안 걸림) |
| ④ 상세 → 뒤로 (390·360, 회귀) | `test_detail_then_back_keeps_list_and_scroll` | 통과 | 통과 |
| ⑤ UX-2 탭 복귀 ('2'→뒤로→달력→차량목록) | `test_tab_return_after_page_back_restores_scroll` | 통과 | 실패 ('2'→뒤로 단계) |
| 지적 2 대조: bfcache 없음 (새 로드 back_forward, 390·360) | `test_page_link_then_back_without_bfcache_restores_scroll` | 통과 | 실패 (3961→313) |
| 추가: Ctrl 클릭 | `test_modified_click_opens_tab_without_hiding_list` | 통과 | 실패 |
| 가치 유지: 느린 망 스켈레톤 | `test_skeleton_still_shows_on_slow_network` | 통과 | 통과 |
| 소스 앵커 2건 | `test_skeleton_iife_*` | 통과 | 실패 |

- ⑥ 폭 390·360 은 위 표에 파라미터로 들어 있다.
- 단언 기준
  - 목록 보임, 스켈레톤 숨김.
  - |scrollTop − 누른 자리| ≤ clientHeight.
  - `nc:scroll` 저장값도 같은 기준. 새 로드로 돌아올 때 이 값을 쓰기 때문이다.
  - persisted=true.
- **작업 트리:** 15/15 통과를 4회 확인했다(35~53초).
- **HEAD 트리** (git archive, web/ 동일): 12 실패 · 3 통과. 통과한 3건(④ 2건, 느린 망)은 기존 동작을 지키는 테스트라 통과가 맞다.
- **변이 시험** (스크래치 HEAD 트리에 변형 템플릿을 넣어 돌렸다)
  - pagehide 되돌림 제거(A 방식): 7/9 실패.
  - `scrollTop=y0` 제거: 9/9 통과. §2 의 Chromium 자가 복원 때문이다. 이 줄은 소스 앵커 테스트만 지킨다.
- **컨텍스트 정리:** 픽스처 `ctxs` 가 단언이 실패해도 컨텍스트를 닫는다. 열린 채 남은 미리 받기 요청이 conftest 가 DB_PATH 를 되돌린 뒤의 서버로 새지 않게 하려는 것이다. HEAD 첫 실행에서 `no such table` 로그를 보고 넣었다.
- **기존 UX 테스트:** 8개 파일(ux1_ux4 · ux2_ux5 · ux3 · ux8 ×2 · ux_batch · ux_round3 · ux9) **238 통과**.
- **전체 스위트:** **2104 passed · 4 xfailed · 0 failed** (9분 46초, `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`). 다른 담당의 미추적 테스트(ops3 등)도 포함된 수다.

## 4. 기계 측정 — 6폭 (확인된 사실, `screenshots/ux9/matrix-6w-after.txt`)
- 조건: 320·360·390·430 은 공개 뷰 모바일, 768·1440 은 관리자 뷰 데스크톱. 목록 첫 화면을 쟀다.
- 가로 스크롤: 0 (6/6).
- 화면 밖 요소: 0 (가로 스크롤 칩 줄·캐러셀 제외).
- '다음 ›' → 뒤로(bfcache): 6/6 통과. 모두 persisted=true, 목록 보임, scrollTop 이 누른 자리와 같다.

| 폭 | 누른 자리 = 뒤로 뒤 |
|---|---|
| 320 | 4546 |
| 360 | 4319 |
| 390 | 4240 |
| 430 | 4152 |
| 768 | 3853 |
| 1440 | 695 |

- 앵커 점프: 해당 없다(앵커를 바꾸지 않았다).
- 레이아웃: 바뀐 것은 스크립트뿐이고 app.css md5 도 같다. 누르기 전 캡처는 before·after 가 바이트까지 같다.

## 5. 캡처 — screenshots/ux9/ (HEAD.txt 에 기준 커밋·dirty·조건·md5 전부 기록)
- 조건: 390×844, DPR 1, 공개 뷰, 새 컨텍스트(서비스워커 허용).
- 모든 캡처는 Read 로 직접 열어 확인했다.

| 파일 | 내용 | md5 |
|---|---|---|
| `ux9-390-before-2-after-back.png` | 변경 전: '다음 ›' → 뒤로. 회색 줄 8개와 '총 1316건'만 있다(persisted=true, top 313) | 09d3a376 |
| `ux9-390-after-2-after-back.png` | 변경 후: 같은 조작. 목록과 페이지 이동 줄이 누른 자리에 있다(persisted=true, top 4240) | 24dca5f6 |
| `ux9-390-after-3-slow-skeleton.png` | 느린 망(page=2 를 서버에서 2.5초 지연): 누르고 0.9초 뒤 스켈레톤 | c858d33a |
| `ux9-390-after-4-apply-back.png` | [적용] → 뒤로: 목록 정상. ⚠ N3 이 보인다(§6) | 42095ee3 |
| `ux9-390-{before,after}-1-before-click.png` | 누르기 전 화면 | 둘 다 760b2542 |

- 누르기 전 캡처 두 장의 md5 가 같은 것은 **예상된 일**이다. 수정과 무관한 화면이고 URL·폭·scrollTop 4240 이 같다.
- 판정의 근거인 짝(before-2 ↔ after-2)은 md5 가 다르다.

## 6. 새로 발견 · 관찰 (범위 밖 — 고치지 않았다)
**N3 (기존 결함, 확인): [적용] → 뒤로 가면 필터 셀렉트에 적용하지 않은 값이 남는다.**
- 증상: 목록은 조건 없는 1페이지(총 30건)인데 제조사 셀렉트가 '기아'로 남는다. [적용] 변경 표시(is-dirty)도 없다. [적용] 스크립트의 `pageshow → mark(false)` 가 떼기 때문이다.
- 사용자에게는 조건이 적용된 목록처럼 보인다.
- 재현 범위: HEAD 와 작업 트리, bfcache 복원과 새 로드 back_forward(Chrome 폼 상태 복원) 모두 똑같다.
- 처방 후보(미검증):
  - pageshow 에서 `form.reset()` 으로 서버 값으로 되돌린다. 또는
  - `mark(false)` 대신 서버가 렌더한 기본값과 비교해 표시한다.
- 티켓 후보: frontend, 낮음~중간.

**관찰 (미검증, 성능): 서비스워커가 제어하는 문서에서 2페이지 이동이 더 오래 걸렸다.**
- 조건: 서버에서 2.5초 지연, 각 N=3.
- 클릭 → 커밋: 서비스워커 제어 6.3~9.9초, 서비스워커 차단 3.7~4.2초.
- 두 경우 모두 page=2 요청이 2건이었다(speculationrules 미리 받기 `other` + `document`).
- 전체 스위트를 동시에 돌리던 때라 수치가 흔들린다. 원인은 확인하지 않았다.
- 성능 담당에게 확인을 권한다.

## 7. 한계
- 헤드리스 Chromium 148 만 썼다.
- **실기기 안드로이드 Chrome·TWA 는 검증하지 않았다.** qa 가 권고한 실기기 1회(목록 1페이지 끝 → '2' → 뒤로)가 남아 있다.
- Safari·Firefox 는 설치돼 있지 않아 보지 못했다.
- §2 의 '남은 1프레임'이 실기기에서 보이는지 모른다.

## 다음 담당 제안 (지시서 규정대로 handoff: [] — Steward 판단용)
- **qa-engineer:** 실기기 1회 재현. 확인할 것: 목록 1페이지 끝 → '2' → 뒤로, [적용] → 뒤로, 상세 → 뒤로.
- **app-design-expert** (공개 화면): 확인할 것:
  - after-2·after-3 을 본다.
  - 남은 1프레임을 없애는 (a) 지연 표시와 (b) 겹침 가운데 무엇을 쓸지, 쓸 필요가 있는지 판단한다.
- **frontend:** N3 을 티켓으로 만든다(Steward).