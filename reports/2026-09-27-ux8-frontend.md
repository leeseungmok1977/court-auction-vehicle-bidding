---
order: 2026-09-27-06
from: frontend-engineer
ticket: UX-8
result: done
verified: 재현
handoff: []
---
# UX-8 결과 화면 필터 카드 접기 — 구현·측정·캡처 (2026-09-27-06 / frontend-engineer)

- 기준 커밋: `c7d38d0`. 작업 트리는 **커밋하지 않았다**(커밋·배포·라이브 요청 없음). 작업 중 HEAD 가 `151ce55`→`c7d38d0` 으로 움직였다(다른 세션의 ops 커밋, 템플릿 무관 — `git show --stat` 로 확인).
- 바꾼 파일: `web/templates/vehicles.html` · `web/static/app.css`(`npm run build:css` — 새 유틸리티 7종) · `tests/test_ux8_filter_fold.py`(신규) · 회귀 테스트 5파일 최소 수정(§5-2). `web/templates/base.html`·`web/app.py`·`web/db.py`·`web/service.py` 는 **손대지 않았다**(git status 확인).
- 측정 조건: 로컬 `127.0.0.1:8917`(금지 포트 회피, 측정 후 종료), `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`, DB 는 `data/auction.db` 를 `mode=ro` 로 열어 `sqlite3.backup` 한 사본(1,418행). 공개 뷰는 `x-forwarded-for`. Chromium 148 headless, DPR 1. 폰(320·360·390·430)은 **844 높이 + is_mobile + has_touch**, 768·1440 은 900 높이. 1440 공개 뷰 = PC 폰 프레임(420 iframe) 안, `1440a` = 관리자 전체 폭.

## [요약]

조건을 건 결과 화면(has_filter)의 폰 폭(< 640)에서 필터 카드가 **서버 렌더부터 접힌다**. `검색 · 필터 — 현대 외 3` 머리만 보이고, 첫 매물 카드 top 이 **HEAD 602.5 → 353.5(−249px)**, 320 은 622.5 → 373.5(−249). 390×844 에서 첫 카드의 최저매각가 줄 하단이 **891(탭바 787 뒤, HEAD 는 863) → 614(첫 화면 안)** 으로 올라온다.
⑤ 는 두 안을 다 만들어 쟀고 **(b)를 골랐다** — 접혔을 때만 해제 칩 한 줄을 카드 밖에 둔다. 이 줄이 가져가는 폴드는 34px(283px 중 12.0%)이고, 320 에서 첫 해제 ✕ 우변 136.6 이 페이드 시작 288 보다 앞이다(UX-4). 판정 규칙 둘 다 통과라 (b)이고, 최종 판정은 디자인 검수에 맡긴다.
넓은 폭(768 공개·1440 관리자)과 큰글씨의 캡처 md5 는 HEAD 표본과 같다. 예외는 768-plain 1장뿐인데, 픽셀 차 32px·채널 최대 차 2(모서리 안티앨리어싱)이고 새 컨텍스트 절차로는 HEAD 와 상태 집합이 같다(§4).
테스트: 신규 39 passed, **전체 1,880 passed · 3 xfailed · 0 failed**(343초, 전 회차 1,837 + 신규 39 + `c7d38d0` 의 순환계 테스트 4).

## 1. 바꾼 것 (앵커 — 줄 번호 없음)

| 앵커 | 내용 | 원칙 |
|---|---|---|
| `<details id="listFilter"{% if not has_filter %} open{% endif %} class="group peer …"` | has_filter 면 **open 없이** 렌더. 조건 없음은 전처럼 `open`. `group`(히트영역 ::before 의 open 변형)·`peer`(접힌 칩 줄 표시)는 스타일 없는 표식 | ① |
| 같은 `<summary class="hidden{% if has_filter %} max-sm:flex{% endif %} …">` | has_filter 일 때만 **sm 미만에서 보임**. 넓은 폭은 전처럼 `hidden`, 큰글씨는 base.html `html.nc-large #listFilter > summary{display:flex}` 가 그대로 이긴다 | ②③ |
| 같은 summary 의 `relative before:absolute before:-inset-x-3 before:-top-4 before:-bottom-3 group-open:before:bottom-0` | 히트영역. summary 는 28px(아이콘 글리프 24 + py-0.5)이라 40px 규칙 미달 → `::before` 로 카드 여백까지 넓혀 **접힘 56px · 펼침 44px**(펼침에서는 아래로 넓히지 않는다 — 바로 밑 셀렉트의 탭을 뺏지 않게). 절대 위치라 bounding box·픽셀 불변(큰글씨 md5 동일 §4) | 접근성 |
| `</details>` 뒤 인라인 스크립트(앵커 `nc:listFilterOpen`) | `fold=!d.open`(서버가 정한 값) → `d.open = !…contains('nc-large') && (!fold \|\| wide() \|\| mem()[key()] === 1)`. 넓은 폭(`matchMedia('(min-width:640px)')`)은 **첫 페인트 전에** 연다. 기억 = sessionStorage `{page·빈 값 뺀 쿼리(키 정렬): 1}`, **summary 를 사용자가 눌렀을 때만** 기록(큰글씨 토글·폭 변화가 여는 것은 제외), 30개 상한. 폭이 640 이상으로 바뀌면(가로 회전) 연다 — 닫힌 채 손잡이 없는 카드를 남기지 않는다 | ②④ |
| `{% macro filter_chips(with_quick) %}` … `{% endmacro %}{{ filter_chips(true) }}` | 카드 안 칩 행의 해제 칩 블록을 **제자리에서** 매크로로 감쌌다. 비활성 퀵 칩 셋(`입찰예정 30일만`·`검사 경과`·`외관 손상`)만 `{% elif with_quick %}`. 렌더 결과는 매크로 전과 **바이트 단위로 같다**(11개 URL 에서 칩 `<a>` 목록 exact 비교) | ⑤⑥ |
| `<div id="listFilterChips" class="flex sm:hidden peer-open:hidden [.nc-large_&]:hidden mt-2 px-1 … overflow-x-auto … mask-image…">{{ _fold_chips }}` | 안 (b). `filter_chips(false)` 로 해제 ✕ 칩만. 표시 조건은 **CSS 만**: 폰 폭 · 접힘 · 일반 모드. 해제 칩이 없으면(제조사·판정만) 줄 자체를 안 그린다. 스크립트 **뒤**라 파싱될 때 최종 open 이 정해져 있다 | ⑤ |
| `<div>{# UX-8 래퍼 … #}` … `</div>` | details·스크립트·접힌 칩 줄을 한 래퍼에. 없으면 `#appscroll` 의 `space-y-6`(특정도 0,3,0)이 칩 줄에 24px 를 붙인다 | 구조 최소 |

base.html 의 스크롤 복원 순서는 **고칠 필요가 없었다**. 인라인 스크립트가 details 바로 뒤에 있어 body 끝의 `function restore()` 보다 먼저 돌고, 렌더 HTML 에서 `nc:listFilterOpen` 이 `function restore()` 보다 앞선다는 것을 테스트로 고정했다. 탭 복귀에서 scrollTop 이 ±1px 로 같은 것도 확인했다(§5 P4).
`ncToggleLarge()`(base.html)는 그대로 뒀다. 큰글씨를 끄면 펼친다. 결과 화면 폰 폭에서는 summary 가 보이므로 다시 접을 손잡이가 있다(P6).

## 2. ⑤ (a)/(b) 비교와 선택

캡처는 `mid-a-*`·`mid-b-*` 이고, 같은 템플릿이라 `mid-b` 는 최종과 md5 가 같다.

| 항목 (확인된 사실, 사본 DB) | (a) 칩은 카드 안 | (b) 접혔을 때만 해제 칩 한 줄 |
|---|---|---|
| 첫 카드 top, cond 360·390·430 (HEAD 602.5) | 319.5 (−283) | **353.5 (−249)** |
| 첫 카드 top, cond 320 (HEAD 622.5) | 339.5 (−283) | **373.5 (−249)** |
| 첫 카드 top, date 360+ (HEAD 635.5) · 320 (651.5) | 352.5 · 368.5 | **386.5 · 402.5** |
| (b) 줄이 먹는 폴드 | — | 26 + mt-2 8 = **34px = 283 의 12.0%** |
| 첫 카드 최저매각가 줄 하단 390 (탭바 787) | 580 (산출: 614 − 34) | **614** (실측) — 둘 다 첫 화면 안 |
| 320 첫 해제 ✕ 우변 ≤ 페이드(줄 우변 − 16 = 288) | 해당 없음(접히면 ✕ 없음) | cond **136.6** · date **148.5** ✓ |
| 조건 하나만 빼기(UX-1) | **2탭**(펼치기 → ✕, ✕ 가 가로 스크롤 뒤면 스와이프 추가) | **1탭** — P3b 가 `price` 만 빠지고 maker·year_min·sort 가 남는 것을 확인 |
| 필터 전부 풀기 | 요약 줄 `필터 초기화` 1탭 | 같음 |
| 회귀 테스트 영향 | 4건(접힘으로 폼·검색 저장이 숨음 — 두 안 공통) | 4건 + 7건("해제 칩 정확히 하나"를 HTML 전체에서 셌다 → 카드 안 칩 행으로 범위 조정, §5-2) |
| DOM | 칩 1벌 | 활성 칩 2벌(매크로 하나, 한 번에 한 벌만 렌더 트리에 있음 — 닫힌 details 내용 / `peer-open:hidden`) |

**선택: (b).** 지시서의 (a) 조건은 "(b)가 폴드 이득을 대부분 먹거나 320 에서 UX-4 를 깨면"이었다. 측정은 12.0%·✕ 우변 136.6 ≤ 288 이라 둘 다 해당하지 않는다. (b)의 비용은 폴드 34px 과 테스트 7건 범위 조정이고, 얻는 것은 UX-1 에서 고친 "조건 하나만 빼기 한 번 탭"이다.
3칩(가격대·연식·주행거리)이면 320·360 에서 줄이 넘쳐 셋째 칩이 페이드 뒤로 간다(`rowOver: true`). 이것은 카드 안 칩 행과 같은 가로 스크롤 규칙이다. 390 은 넘치지 않는다.

## 3. 측정표 (확인된 사실 — `measure_ux8.py`, 폰 844 높이)

| 뷰 | URL | 상태 | 필터 하단 | summary h / 히트 | 접힌 칩 줄 | 첫 카드 top (HEAD) | 가로 스크롤 |
|---|---|---|---|---|---|---|---|
| 320 | cond | 접힘 | 134 (417) | 28 / 56 | 26, ✕ 136.6 ≤ 288 | 373.5 (622.5) | 없음 |
| 360·390·430 | cond | 접힘 | 134 (417) | 28 / 56 | 26 | 353.5 (602.5) | 없음 |
| 320 / 360+ | date | 접힘 | 134 | 28 / 56 | 26, ✕ 148.5 | 402.5 / 386.5 (651.5 / 635.5) | 없음 |
| 폰 4폭 | cond·date | 펼침(탭) | 445 (417) | 28 / 44 | 숨음 | **HEAD +28** (630.5 / 650.5 등) | 없음 |
| 폰 4폭 | plain | 펼침(조건 없음) | 417 (417) | 숨음 | 없음 | 576.5 (576.5) **무변경** | 없음 |
| 768 | cond·date·plain | 펼침 | 266·238·238 (같음) | 숨음 | 숨음 | 451.5·456.5·397.5 (같음) | 없음 |
| 1440a | 3종 | 펼침 | 242·208·208 (같음) | 숨음 | 숨음 | 같음 | 없음 |
| 1440 공개(프레임 420) | cond·date | **접힘** | 134 | 28 / 56 | 26 | 353.5 / 386.5 | 바깥·안 없음 |
| 큰글씨 320·360 | cond·date | 접힘 | 162 (162) | 30 / 65 | 숨음 | 520.3·556.3 / 508.3·544.3 **무변경** | 없음 |

- 펼침 비용: 펼친 카드는 HEAD 보다 **28px 크다**(맨 위 summary 줄). 사용자가 펼쳤을 때만 치른다.
- 접힌 머리 잘림(`scrollWidth > clientWidth`): 일반 모드에서는 **320 + 첫 부품이 날짜**일 때만 `— 2026-09-01 매각 외 1` 이 147px 필요·143px 표시로 `외 1` 이 잘린다. 가격대 첫 부품 `— 1,000~2,000만 외 3`(135)·법원·검색어는 320 에서도 온전하다. 바로 아래 요약 줄이 전문을 보이므로 정보가 사라지지는 않는다. 다만 **DES-3 이 일반 모드 320 까지 넓어졌다**(§6).
- 1440 공개 뷰가 접히는 것은 규칙대로다(프레임 안 폭 420 < 640). 지시서 ⑺ "1440 에서 open" 은 관리자 전체 폭(1440a)에서 성립한다(§6-1).

## 4. 캡처 (`screenshots/ux8/`, 45장 + `HEAD.txt` — 기준 커밋 `c7d38d0` + dirty 목록 + 조건 + 전 md5 + 해시 관계)

| 요구 | 파일 (md5 앞 8자리) | 판정 |
|---|---|---|
| before/after 360·390 (cond) | `before-360-cond` 389f5d03 → `after-360-cond` b89edb8a · `before-390-cond` 49ade9d0 → `after-390-cond` 779c0781 (+ 320: 51cd13bb → 45db702d, 360-date: d854b1c6 → fb652ac3) | **상이** ✓ |
| (a)/(b) mid 320·360 | `mid-a-320-cond` 1fcd2e7d · `mid-a-360-cond` 6efdab43 · `mid-b-320-cond` 45db702d · `mid-b-360-cond` b89edb8a (+ date 4장) | a≠b ✓, mid-b = after(같은 템플릿) |
| 펼친 상태 360 | `after-expanded-360-cond` 3c5a1974 (= `mid-a-expanded` — 펼치면 (a)·(b) 동일) · 390 4bd8d914 | — |
| 768·1440 무변경 | after = HEAD 표본: 768-cond 10dee57f · 768-date f34babe0 · 1440a-cond c30137d1(= `detcheck`/`headre`) · 1440a-date 6ea0e75b · 1440a-plain 32c4bb47 | **일치** ✓ |
| 〃 예외 | `after-768-plain` 2c2e7b96 ≠ `before`/`headre` 61d19cf9 — 픽셀 차 **32px, 채널 최대 차 2**, 셀렉트 윗모서리(y93~95)·카드 우하단 모서리 안티앨리어싱뿐 | 아래 대조군 |
| 큰글씨 360 | `after-large-360-cond` cdd002e8 · `-date` 61a1a060 = before | **일치** ✓ (히트영역 ::before 가 픽셀을 안 바꾼다는 증거) |
| 1440 공개(프레임) | a866bb61 → 82c98827 | 상이(프레임 안이 접힘 — §6-1) |

**md5 가 같다/다르다는 말을 정직하게 하려고 대조군을 찍었다.** HEAD 자체가 넓은 폭에서 한 가지 md5 로 찍히지 않는다. 같은 HEAD 에서 1440a-cond 가 `408446e3`/`c30137d1`, 768-cond 가 `10dee57f`/`11fd9cce` 로 갈렸다(셀렉트 글자 줄 2,882px — 눈으로는 같다. `scratchpad cmp768.png` 로 확인).
그래서 템플릿·app.css 를 HEAD 로 되돌려 **새 컨텍스트 절차로 5회씩** 찍고, 최종으로 복원해 같은 절차로 다시 5회씩 찍었다.

| 캡처 | HEAD ×5 | 최종 ×5 |
|---|---|---|
| 768-plain | 9d53a5a6×3 · 61162cb6×2 | 9d53a5a6×4 · 61162cb6×1 — **같은 집합** |
| 768-date | c7cbbf80×4 · f34babe0×1 | c7cbbf80×5 |
| 768-cond | 10dee57f×5 | 10dee57f×2 · 11fd9cce×2(HEAD 순차 절차에서 2회 관측) · b3e748c1×1 |
| 1440a-cond | c30137d1×4 · 408446e3×1 | c30137d1×5 |
| 1440a-date · plain · 큰글씨 cond · date | 한 가지씩 | HEAD 와 같은 값 |

`b3e748c1` 한 건만 HEAD 표본에 없다. 10dee57f 와의 차는 66px·채널 최대 13·y439~442 의 65×3 띠이고, **추정**으로는 래스터 비결정성이다(HEAD 에서 같은 절차로 5회 중 미관측이라 단정하지 않는다).
**눈으로 연 것(Read)**: before-390-cond · before-768-cond · mid-a-360-cond · mid-a-expanded-360-cond · mid-a-320-date · mid-b-360-cond · mid-b-320-cond · after-390-cond · after-expanded-390-cond · after-1440-cond · after-1440a-cond · after-large-360-cond. 파일명과 화면이 일치하고, 대상(필터 카드·접힌 칩 줄·첫 카드)이 프레임 안에 있다.

## 5. 테스트 (확인된 사실 — pytest 출력)

- `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1 python -m pytest tests/` → **1,880 passed · 3 xfailed · 0 failed** (343초).
- 파일별(junit): test_ux8_filter_fold **39** · test_ux2_ux5_nav_state 33 · test_ux_round3 23 · test_ux1_ux4_form_and_chips 23 · test_feat1_price_select 21 · test_feat2_year_km_select 30 · test_feat1_qa_adversarial 33 + 2 xfail · test_feat2_qa_adversarial 104 + 1 xfail · test_panel_r3_large_toggle 3 — 전부 초록.

### 5-1. `tests/test_ux8_filter_fold.py` (앵커 문자열만, 오프셋 창 없음)

- 템플릿 19: has_filter → open 없음·`hidden max-sm:flex`·히트영역 클래스·`— 현대 외 3`·title 전문 / 조건 없음(`/vehicles`·`sort=`·`page=2`) → `open`·`hidden`·칩 줄 없음 / 날짜 `— 2026-09-01 매각 외 1` / 접힌 칩 줄 == 카드 안 해제 ✕ 칩(11 URL — 검색 저장·초기화·비활성 퀵 칩 없음) / 해제 칩 없는 조건(제조사·판정·차종)이면 줄 없음 / 줄 클래스와 래퍼 안 순서 / 매크로 1정의·2호출·칩 title 소스 1회 / 스크립트 규칙과 `function restore()` 보다 앞 / app.css 규칙 7종.
- Playwright 20:
  - P1 폰 4폭: 접힘·머리·✕ ≤ 페이드·히트(elementFromPoint 로 글자 줄 위 12·아래 10 이 summary)·탭 펼침(아래 셀렉트 탭은 안 뺏음, 히트 ≥ 40)·이득 ≥ 200·재탭 접힘.
  - P3: 펼침 → 2페이지 펼친 채 → 뒤로 펼친 채 → 정렬 바꿔 [적용] 접힘 → 같은 조합 [적용](빈 값 URL) 펼친 채 → 카드 안 칩 ✕ 접힘.
  - P3b: 접힌 줄 칩 1탭이 그 키만 뺀다.
  - P4: 탭 복귀 접힌 채/펼친 채 × URL·scrollTop ±1.
  - P5: rAF 매 프레임 기록 == 최종 == DOMContentLoaded — 폰 기본·기억·조건 없음·큰글씨·768·1440.
  - P6: 큰글씨 무변경 + 끄면 펼침·손잡이 남음·기억 안 씀.
  - P7: 640·768·1440 open·summary/줄 숨김.
  - P8: 639 접힘 → 844 로 회전 시 열림.
  - P9: 펼친 뒤 검색 저장 라벨.
- **공허 통과 점검**:
  - HEAD 템플릿으로 돌리면 **30 failed · 9 passed**. 통과 9건은 무변경 가드(조건 없음·CSS·P5 plain/large/wide·P7)라 HEAD 에서도 통과가 맞다.
  - P5 가 번쩍임을 실제로 잡는지 보려고 스크립트를 `setTimeout(…, 200)` 으로 늦춘 변이체를 만들었다. **3 failed**(기억·768·1440)로 잡혔고, 원본으로 복원했다.

### 5-2. 회귀 테스트 최소 수정 (범위 밖 파일 — 동작 변경의 직접 결과라 고쳤다)

| 파일 | 수정 | 이유 |
|---|---|---|
| `test_ux_round3.py` | `test_apply_dirty_reverts…`·`test_saved_search_label_runtime_reads_new_keys` 에 summary 탭 1줄 | 390 결과 화면은 카드가 접혀 셀렉트·검색 저장이 숨는다. 사용자처럼 편 뒤 조작한다 (a)·(b) 공통 |
| `test_feat1_price_select.py` · `test_feat2_year_km_select.py` · `test_feat1_qa_adversarial.py` · `test_feat2_qa_adversarial.py` | 헬퍼 `_card_chip_row(html)`(앵커 `<div class="nc-chiprow` ~ `</form>`)로 칩 수를 **카드 안 칩 행**에서 센다 | (b) 에서 같은 칩이 HTML 에 두 번 있다. 두 줄의 동일성은 신규 파일이 따로 고정한다 |

단언 내용(수·문구·href·톤)은 **한 글자도 바꾸지 않았다**. 바꾼 것은 세는 범위뿐이다.

## 6. 못 한 것 · 발견 (Steward 판단용)

1. **1440 공개 뷰는 접힌다.** PC 폰 프레임(iframe 420)이 폭 규칙상 폰이다. 지시서 ⑺ "1440 에서 open" 은 관리자 전체 폭에서만 성립한다. 프레임 = 폰 화면이라 일관된다고 보지만 **Steward 확인이 필요하다**. 프레임만 예외로 하려면 `window.self !== window.top` 분기가 필요하다(지금 넣지 않았다).
2. **DES-3 범위 확대.** 접힌 머리가 이제 일반 모드에서도 보여서 **320 + 첫 부품 날짜**면 `외 1` 이 잘린다(147 필요·143 표시, §3). 백로그 DES-3 본문에 "일반 모드 320(UX-8 이후)"과 근거 캡처 `mid-a-320-date.png`·`mid-b-320-date.png` 를 더할 것을 권고한다. 처방은 DES-3 그대로다.
3. **검색 저장이 결과 화면 폰 폭에서 한 탭 더 깊다.** 지시서 (b) 정의대로 접힌 줄에 넣지 않았다. 리텐션 장치라 사용량 영향은 **미검증**이다.
4. 실기기(TWA·안드로이드 Chrome) 확인은 하지 않았다. 헤드리스 is_mobile·has_touch 까지만 했다.
5. 큰글씨를 끄면 `ncToggleLarge()` 가 펼친다. 그 조합의 기본값(접힘)과 다르지만, 다음 로드부터는 규칙대로다. base.html 은 범위 밖이라 그대로 뒀다.

## 7. 디자인 검수에 물을 것

1. **(a) vs (b) 최종 판정** — §2 표. 34px(12%)로 "조건 하나만 빼기 1탭"을 사는 것이 맞는가.
2. 접혔을 때 같은 조건이 **세 번** 말해진다: 머리 `— 현대 외 3` · 해제 칩 줄 `1,000~2,000만 ✕ 2018년 이후 ✕` · 요약 줄 `현대 · 1,000~2,000만 · 2018년 이후 · 매각기일순 · 필터 초기화`(`after-390-cond.png`). 중복으로 읽히는가, 역할(요약/손잡이/전문)이 갈려 읽히는가. 제조사는 해제 칩이 원래 없어서 머리 `외 3` 과 칩 2개의 수가 다르다.
3. 펼친 상태의 머리 줄(+28px)과 **고정된 `expand_more`**(`after-expanded-390-cond.png`). 큰글씨 때부터 같은 모양이다. 펼침에서 셰브런을 뒤집을지 — 한다면 transform 만, reduced-motion 존중.
4. 히트영역 `::before` 가 카드 위 테두리 밖 3px 까지 나간다(접힘 56·펼침 44). 시각 변화는 0 이다(큰글씨 md5 동일).
