---
order: 2026-09-27-56
from: pm-orchestrator
ticket: KCAR-1
result: blocked
verified: 재현
handoff:
  - to: steward
    why: docs/backlog.md 쓰기가 헤드리스에서 거부됨 — 본 보고서 §2 (가)~(마) 문안을 백로그에 옮기면 이 지시서는 done (KCAR-3·KCAR-4·AUD-03 보강, KCAR-5·DES-6 신규)
  - to: frontend-engineer
    why: KCAR-4(+DES-6) — detail.html '소매 시장 대비 차익' 카드를 비유의 물건에서 중립색·만원 단위로, 초록은 tone=='ok' 만, 라벨 '평균'→'중앙값' 통일, 390·1440 캡처(기준 커밋 병기) 후 교차검수 2자리
  - to: backend-engineer
    why: PANEL-22 — app.py::watchlist 에 bid_state 를 태우고 목록과 같은 판정인지 회귀 테스트(KCAR-3 선결)
---

# KCAR-1 후속 티켓화 — pm-orchestrator (당직 Steward 가 대신 기록)

2026-09-29 당직(헤드리스). 지시서 `2026-09-27-56`. 입력: `reports/2026-09-27-kcar1-app-design-expert.md` §3·§5(3)·§7, `reports/2026-09-27-audit-critic.md` N-1, `docs/backlog.md`.

## [요약]
검수 항목 5건 중 **3건은 이미 티켓이 있다**(F1→KCAR-3, F2→KCAR-4, N-1→AUD-03). **신규는 2건**이다(F3→KCAR-5, 어휘 불일치→DES-6).
그런데 pm 의 `docs/backlog.md` 편집이 권한 거부로 **0건**이다. 그래서 result 는 `blocked` 로 둔다. 넣을 문안은 §2 에 있다.
이번 실행에서는 코드·설정 편집, 커밋, 배포를 하지 않았다.

## 1. 항목별 판정

| 항목 | 티켓 | 재현(pm) | Steward 재확인 | 배정 제안 | 착수 조건 |
|---|---|---|---|---|---|
| F1 즐겨찾기가 판정 변화를 반영하지 않음 + 저장 입찰가와 상한을 대조하지 않음 | **KCAR-3**(기존, 흡수) · 선결 **PANEL-22** | 코드 재현. 카니발 10111 수치(여유 +1,900,000)와 즐겨찾기 렌더는 **미검증** | ✔ `app.py::watchlist` 는 `expected_for`·`_display_judgment` 만 부르고 `bid_state` 는 부르지 않는다. 백로그 KCAR-3·PANEL-22 행이 있다 | PANEL-22 backend → KCAR-3 frontend | UX-8 완료(`3a5cd7c`, 백로그 확인)로 잠금 해제. PANEL-22 가 먼저 |
| F2 판정은 앰버인데 차익 카드는 초록 + 원 단위 | **KCAR-4**(기존) | 코드 재현 | ✔ `detail.html` 의 `{% if use and use.saving %}` 바로 뒤가 `text-emerald-600` 이고 `use.saving\|won` 을 쓴다 | frontend | 없음 |
| F3 부적합 문단 끝에 묻힌 사고이력 단서 | **KCAR-5**(신규 안) | 코드 재현. "390 에서 9줄 중 4줄"은 **미검증**. 고정 테스트 0건도 **미검증** | ✔ `service.py::plain_verdict` 안에 "무사고로 확인되면 상한선이 … 이번 회차도 검토 가능해집니다" 문장이 있다. 문단 결합 구조는 pm 진술(미재확인) | backend(반환 키 분리) → frontend | 없음 |
| audit N-1 '높음' 초록 알약 vs '근거 약함 · 22일 전' | **AUD-03**(기존, Steward 재현 완료) | 표시 쪽 코드 재현 | ✔ 백로그 AUD-03 행이 있다(오너 승인: 판정 기준). `cbadge` 분기는 미재확인 | backend/frontend | 점수·게이트는 **오너 승인** |
| 별건 '소매 평균 시세' vs '중앙값(가운데 값)' | **DES-6**(신규 안) | 코드 재현 | ✔ `detail.html` 라벨 `소매 평균 시세` 가 `eff_median` 을 표시한다. "템플릿 전체 유일"은 미재확인 | frontend(KCAR-4 와 같은 커밋 가능) | 없음 |

- 교차검수: 5건 모두 숫자·판정 표시다. **app-design-expert + design-critic 둘 다** 필요하다.
- ⚠ KCAR-4 색 처방이 두 곳에서 다르다. 백로그는 **앰버**, 검수 보고서 F2 는 **중립**이다.
  - pm 권고는 중립이다. 히어로가 이미 앰버라서 한 화면에 앰버를 두 번 켜지 않기 위해서다.
  - 교차검수에서 확정한다.

## 2. docs/backlog.md 에 옮길 문안 (pm 작성 · 미반영)

**(가) KCAR-3 행 끝에 추가**
> ★ 2026-09-29 pm(지시서 2026-09-27-56): app-design-expert KCAR-1 검수 §3 **F1** 을 이 티켓으로 흡수(신규 없음 — 출처 표기의 'F2' 는 그 보고서에서 F1). 코드 재현: `base.html` `Notes.paint` 는 값만 채우고 입찰 상한과 비교하지 않음 · `app.py::watchlist` 는 `bid_state` 없이 `_display_judgment` 만 · `watchlist.html` '여유'는 `margin_room>0` 이면 판정 무관 초록. 카니발 10111 수치와 즐겨찾기 렌더는 미검증. **DoD 보강**: ① 상세 입찰 메모 칸 아래 + **즐겨찾기 행**에 '저장한 최종 입찰가가 지금 입찰 상한보다 N원 높음' 한 줄(기기 안 처리만 — 로그인·서버 저장·수집 범위 불변) ② 즐겨찾기 판정 칩·'여유' 색을 bid_state 톤으로 ③ 회귀 테스트(저장값>상한·≤상한·상한 없음, 즐겨찾기=목록 같은 톤). **선결 PANEL-22**. 착수 조건 UX-8 완료(`3a5cd7c`)로 충족. 손댈 파일: `app.py::watchlist` → `base.html`·`detail.html`·`watchlist.html`. 교차검수 2자리

**(나) KCAR-4 행 끝에 추가**
> ★ 2026-09-29 pm: 검수 §3 **F2** = 이 티켓. 코드 재현: 차익 블록 `{% if use and use.saving %}` 가 무조건 `text-emerald-600`·원 단위·초록 알약·초록 `savings` 아이콘. ⚠ 색 처방이 이 티켓(앰버)과 보고서(중립)에서 다름 — pm 권고 중립, 교차검수에서 확정. 초록은 `tone=='ok'` 일 때만. DoD 보강: 비유의(G80 50102)·유의 물건 각 1건 390·1440 캡처(기준 커밋 병기) + 만원 반올림 회귀 테스트. 라벨 어휘는 DES-6(같은 커밋 가능)

**(다) KCAR-4 아래 새 행**
> | KCAR-5 | 부적합(로즈) 판정 문단 끝의 사고이력 단서를 판정 칩 아래 **별도 중립 한 줄**로 분리 — 판정 기준은 그대로 | backend · frontend · 교차검수 | todo · P2 | 검수 §3 F3. 재현: `service.py::plain_verdict` blocked 분기가 `alt` 를 `text` 끝에 붙임 → `detail.html` 히어로·`report.html` 한줄 판정이 한 문단. 고정 테스트 0건. **DoD**: ① `plain_verdict` 가 단서를 별도 키(예 `caveat`)로 ② 두 템플릿이 칩 아래 중립 한 줄로(행동 앞: '사고이력 미확인 → 사고차로 가정 · 무사고 확인 시 상한 N원') ③ `bid_state`·`use_accident_rate`·`personal_use_max_bid` 무변경, 판정 동일성 테스트 ④ 단서 있음/없음 테스트 ⑤ 이 분기가 실제로 그려지는 물건으로 320~1440 캡처. 손댈 파일 `service.py`·`detail.html`·`report.html`. 교차검수 2자리 |

**(라) DES-5 아래 새 행**
> | DES-6 | 상세 차익 카드 라벨 '소매 **평균** 시세'가 실제로는 중앙값(`eff_median`)이고, 같은 페이지 근거 카드는 '중앙값(가운데 값)' — 어휘 불일치 | frontend · 교차검수 | todo(낮음) | 검수 §7 끝 별건. 재현: `detail.html` 라벨 `소매 평균 시세`(템플릿 전체 유일) vs `service.py` `"method"` 중앙값. DoD: 라벨을 근거 카드 어휘로 통일 + 전 템플릿 '평균 시세' 0건 테스트. KCAR-4 와 같은 커밋 가능 |

**(마) AUD-03 행 끝에 추가(새 ID 없음)**
> ★ 2026-09-29 pm: KCAR-1 검수 §5(3)이 같은 충돌을 G80 '높음 87/100' vs '근거 약함 22일 전'으로 재확인. 재현: 히어로 `cbadge` 가 `cl=='높음'` 이면 `bg-emerald-400`, 나이를 보지 않음. 범위를 셋으로 나눔 — ⑴ 표시: 알약에 시세 나이 병기, 21일 넘으면 초록 끄기(**자율**) ⑵ 점수·게이트에 나이 반영(**오너 승인**) ⑶ 재조회 경로(C.4 상한 안). ⑴ 을 먼저 착수 가능

## 3. 오너 승인이 필요한 부분
- **AUD-03 ⑵**: 신뢰도 점수나 게이트에 시세 나이를 넣는 것은 판정 기준 변경이다. ⑴ 표시 수정은 자율이다.
- **AUD-03 ⑶**: 시세가 있는 물건을 재조회하는 경로는 외부 요청 수를 늘린다. 런당 상한을 오너가 확인해야 한다.
- F1·F2·F3·DES-6 은 표시만 바꾸고 판정 기준은 그대로다. 승인 대상이 아니다.
  - F1 은 기기 안에서만 처리한다는 조건이 붙는다. 개인정보 수집 범위를 바꾸지 않는다.

## 4. 순서 (pm 제안)
한 번에 한 티켓씩 한다.
1. **KCAR-4(+DES-6)** → frontend. 가장 작고 착수 조건이 없다.
2. **PANEL-22** → backend.
3. 그 뒤 **KCAR-3**, 이어서 **KCAR-5** 를 배분한다.

frontend·backend 모두 `자동: 아니오` 자리다. 그래서 **오너 세션에서** 처리한다.

## 5. 검증 메모 (Steward)
- **재현(코드 grep·Read)**:
  - `app.py::watchlist` 에 `bid_state` 호출이 없다.
  - `detail.html` 의 `use.saving` 블록이 emerald 로 고정돼 있다.
  - `detail.html` 에 `소매 평균 시세` 라벨이 있다.
  - `plain_verdict` 에 무사고 단서 문장이 있다.
  - 백로그에서 KCAR-3·KCAR-4·AUD-03·PANEL-22 행이 있고, UX-8 이 완료(`3a5cd7c`)임을 확인했다.
- **미검증**:
  - 카니발 10111 즐겨찾기 렌더와 수치
  - 390 폭에서의 9줄/4줄
  - `plain_verdict` 가 단서를 `text` 끝에 붙이는 결합 구조
  - `cbadge` 분기
  - '평균 시세'가 템플릿 전체에서 유일한지
  - 관련 고정 테스트 0건
- 라이브·DB 는 조회하지 않았다.
