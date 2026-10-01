---
order: 2026-10-01-35
from: frontend-engineer
ticket: REC-15
result: done
verified: 재현
handoff: []
---

# REC-15 화면 짝 — 리포트 09 칩 · 상세 '사고판정' 말풍선 (frontend-engineer, 지시서 2026-10-01-35)

> Steward 옮김(2026-10-02 00시): 담당은 하네스 규칙상 reports/ 에 쓰지 못해 본문을 인계 메시지로 보냈다. 요지·수치 그대로.
> 기준 HEAD 9078af0(작업 중 이동 없음) 위 미커밋분 REC-13(detail.html · test_rec13_frontend.py) + REC-15 backend(service.py f21990a0 · calculator.py 4507f450 · maint.py 01d53178 · test_rec15_accident_evidence.py · 고친 테스트 4) 위에 손질. 전 = w0(손질 직전 작업 트리), 후 = w1. 커밋·push·배포·ssh·외부 요청 0, 서버 코드 무수정, data/·8765 무접촉.

## [요약]
- **리포트 09 칩**: `{%- set _accl = v|accv %}` 위에서 초록 'ok'·'이력상 양호'는 `_accl == '무사고'` 일 때만, STOP 갈래 그대로 먼저. 주석의 "초록은 이력이 실제로 있고 양호할 때만"을 새 근거로(근거 정의는 `service.accident_evidence` 에만, 템플릿은 글자를 따름).
- **상세 '사고판정' 말풍선**: 기존 두 문장 뒤에 Steward 문구 그대로(둘째 인자 겹따옴표 — 렌더 말풍선·aria-label 두 곳, 홑따옴표는 `&#39;`).
- 테스트: 변경 단언 13개 w0 에서 13/13 빨강(HEAD 9078af0 코드만으로도 13/13 — REC-15 꼴 3개는 전제에서, REC-15 의존), 대조군 5 초록, 변이 9/9 KILLED, 전체 스위트 **2,978 passed · 5 xfailed · 0 failed · 0 skipped**(760초, 노드 2,968 → 2,983).
- 전수 렌더 대조(w0 ↔ w1, 4벌 = 10-01·09-29 사본과 각각 재산정 적용본): 바뀐 쪽 = 모든 상세(공개·관리자, 말풍선) + 리포트 09 칩 6쪽(09-29 5쪽), 두 조각을 가리면 모든 쪽 같음, 리포트 09 초록은 근거 있는 '무사고' 1대(100009)뿐. app.css 재빌드 d1109243.
- 판단 거리: 말풍선이 페이지에서 가장 길어졌다(159자) — 큰글씨 320×640 에서 아래 36px 가 스크롤 영역 밖(굴리면 닿음).

## 바꾼 파일 (w0 → w1)
| 파일 | 전 | 후 |
|---|---|---|
| web/templates/report.html (CRLF) | cc25f05d | e4508e49 |
| web/templates/detail.html (CRLF) | 7fad0a9a | 081acb39 |
| tests/test_exposure.py | 4dd209da | 1d39856f |
| tests/test_rec13_frontend.py | 4532daf2 | b94f75b1 |
| tests/test_rec1_floor_view.py | 8bc6bd06 | 028fe3ee |
| tests/test_rec15_frontend.py | — | 58e27576(새) |
| web/static/app.css | d1109243 | 같음 |
배포 단위(9078af0 대비): REC-15 backend 7파일 + 새 테스트 · 템플릿 2(detail · report) · 테스트 새 2(test_rec13_frontend · test_rec15_frontend) + 고친 2(test_exposure · test_rec1_floor_view) · app.css 없음.

## 항목 (요지)
- 리포트 09: 바뀐 물건 10-01 사본 6대(50904 · 52708 · 50311 · 503268 · 10294 · 43089 — 모두 등급 none·보험이력이 소유자·번호 변경 또는 특수사고 카운트만), 60319·51820 은 09 행이 없음. 같은 행 칸 글자 = 칩 규칙 위반 4벌 모두 0. `test_exposure` 핀: `"insurance_history" in expr` → `"_accl" in expr`, `'ok'\s+if\s+v\.insurance_history` → `'ok'\s+if\s+_accl\s*==\s*'무사고'`, 단언 추가(칩 앞에서 `_accl` 이 `v|accv` 로 정해지는가), 독스트링 옛 규칙은 '5회차 처방'으로. 패리티 테스트에 REC15_OWN(소유자·번호만)·REC15_SPC(특수사고만) — 두 화면 모두 앰버 '이력 미확인'. 픽스처 주석 두 곳의 '근거 있는 none' 예 50904 → 100009(REC-15 뒤 거짓이 되므로, 규칙 8).
- `test_rec1_floor_view.py::test_non_guard_render_is_byte_identical_to_before` — '물건정보' 구역에 말풍선이 들어 있어 의도대로 바뀜 → 그 파일 주석대로 재측정(g90_1 fb500dcd → 02bc9088, sm6_1 81728f90 → 2b182f91), 예전 값은 `_PLAIN_MD5_PRE_REC15` 로 보존, 새 테스트 `…differs_only_by_rec15_gloss_sentence`(새 문장 두 곳만 지우면 예전 md5).
- ⚠ 그 전 회차(23:47 시작)는 자정을 넘겨 7 failed — 2 는 floor_view md5(위에서 고침), 5 는 `test_ux3_sort_rules`·`test_ux_batch_qa_adversarial` 날짜 경계 테스트(HEAD·w0·w1 모두 자정 뒤 단독 실행 초록 — 스위트가 자정을 넘기면 깨지는 기존 취약점).
- 전수 대조: 10-01(c3a96d28) 4,837쪽 다름 3,180 = 상세 3,174 + 리포트 6 / 10-01 재산정(b226bb81) 같음 / 09-29(44a3f8d3) 4,650쪽 3,055 = 3,050 + 5 / 09-29 재산정(25153ab0) 같음 — 가림 md5 ≠ 0, 규칙 위반 0. 리포트 09 분포(w1, 10-01): 앰버 674 · STOP 350 · 초록 1. 재산정 사본: 10-01 미리보기 checked 1,587 · targets 4 · skipped closed 512·flood 5·no_breakdown 355·already 711(backend 와 같음), `--ids … --apply` applied 4, 재실행 targets 0 / 09-29 targets 3(52708 없음).
- 캡처 `screenshots/rec15/`(HEAD.txt md5 354666c9, 촬영 w0 23:55:30~23:57:12 · w1 23:57:23~23:59:11): r50904-row09-N390 bda1a559 → 21a2371d(초록 '이력상 양호' → 앰버 '이력 미확인') · r100009-row09-N390 7a6a8522 같음(대조군) · d50904-accpop-N390 c59df54c → 2b4a0521(말풍선 210×92 → 210×167) · d50904-accpop-L320 7224ff6b → a8685dcf(210×142 → 210×266) · d50904-bdline-N390 bb10fbdd 같음(재산정 후 '사고등급 이력 미확인 — 사고차 가정(감가 15.0%)'). 9장 Read.
- 측정: 6폭 + 큰글씨 가로 넘침 0·화면 밖 0. 말풍선 popcheck(gloss 8개를 화면 가운데로 굴려 열고 #appscroll 아래끝과 비교): 큰글씨 320×640 69자 142px → 159자 266px **넘침 36px**(페이지 다른 말풍선 최대 192px) · 보통 320×640 92 → 167px 넘침 0 · 큰글씨 360×780 넘침 0. 고정 요소 겹침 0, 연 채로 60px 굴리면 열린 채 넘침 0(프로그램 스크롤 — 실제 터치 미검증). 대비: 리포트 09 앰버 #B45309/#FDF3E3 4.57:1(예전부터의 '이력 미확인' 칩, 10.5px 굵게 — AA 근접) · 초록 4.88 · STOP 5.19 · 상세 앰버 4.84.

## 발견 · 판단 거리
1. 말풍선 길이(위) — 차단 아님. 선택지 (가) 그대로 (나) gloss 가 아래 공간이 모자라면 위로 열기(공용 컴포넌트) (다) 문구 줄이기.
2. [실데이터 0대] 칩 문구가 '무사고'가 아니면 모두 '이력 미확인' — 근거 있는 단순수리(minor)·등급 없음('—')도 앰버 '이력 미확인'(전엔 초록 '이력상 양호'). 색 규칙은 맞지만 문구가 이력을 확인한 경우와 어긋난다 — 10-01·09-29 사본 해당 0대, 테스트는 색 규칙만 고정(MINORI 합성).
3. [테스트 취약] 스위트가 자정을 넘기면 날짜 경계 테스트 5개 실패(이번 변경과 무관).

## 확인 · 추정 · 미검증 (요지)
확인: 편집 바이트, 재빌드 md5, 빨강 수(w0·HEAD), 변이, 스위트·노드, 전수 대조 4벌 × 2트리, 재산정 명령·멱등, 캡처 md5·Read, 측정, 말풍선 높이·잘림·스크롤, 대비, HEAD 고정, data/ 파일 수. 추정: data/ 변경 4파일은 순환계·8765. 미검증: 실제 폰·TWA·인쇄, 실제 터치 스크롤, 배포·서버 재산정 뒤 라이브.
스크래치 `scratchpad/rec15_fe/`(hx · serve15 · reprice15 · sweep15 · cmp15 · cap15 · popcheck · scrollcheck · mut15 · suite15, 사본 d1001r · d0929r, out\).

> **Steward 판정(00:10)**: 판단 거리 1 → **(다) 문구를 줄인다**(내가 쓴 문장이 길었다): `'이력 미확인'은 사고 기록을 확인하지 못했다는 뜻이에요. 사고차라는 뜻은 아니고, 가격만 사고차로 가정해 계산합니다.` · 2 → 실데이터 0대, REC-12 에 기록(minor 는 지금 파서가 만들지 않음) · 3 → TEST-5 신규.

## 추가 — 말풍선 셋째 문장 줄임 (Steward 확정 문안, 00:45~01:03)
- 문구: `'이력 미확인'은 사고 기록을 확인하지 못했다는 뜻이에요. 사고차라는 뜻은 아니고, 가격만 사고차로 가정해 계산합니다.` — detail.html 081acb39 → **4a94bb53**, test_rec15_frontend 58e27576 → 4de3cacc, test_rec1_floor_view 028fe3ee → 0539de3b('물건정보' md5 g90_1 → 72b578bc, sm6_1 → d33183af, `_GLOSS_REC15` 새 문장 — 두 곳만 지우면 REC-15 이전 md5 fb500dcd·81728f90 그대로), app.css d1109243.
- popcheck: 보통 320 167 → 148px(넘침 0) · 큰글씨 360×780 넘침 0 · **큰글씨 320×640 넘침 36px 그대로**(16px·폭 210px 에서 10줄 — 한글 낱말 단위로 접혀 23자를 줄여도 줄 수가 같음). 넘침 0 이 되려면 셋째 문장이 큰글씨 약 3줄(36~40자) 안이거나 공용 gloss 가 위로 열려야 한다(추정).
- 관련 7파일 192 passed · 전체 스위트 **2,978 passed · 5 xfailed · 0 failed · 0 skipped**(00:46:43~01:03:00, 자정 안 넘김 · 가드 0) · 날짜 경계 5개(8노드) 01:03 단독 재실행 8 passed. 렌더 대조(첫 문안 ↔ 줄인 문안, 재산정 10-01 사본): 다른 쪽 = 모든 상세 3,174(공개 1,587·관리자 1,587), 문장을 가리면 같음, 리포트 09·그 밖 0. 캡처 `after2/` d50904-accpop-N390 2b4a0521 → 90f6a277(210×167 → 148) · L320 a8685dcf → 7aef208f(266 그대로), Read 확인 잘림 없음, 측정 넘침 0. HEAD.txt md5 256c2ac8.
- **Steward 판정(01:10)**: 큰글씨 320 의 36px 는 받아들인다 — 굴리면 닿고(scrollcheck), 가로 넘침·고정 요소 겹침 0, 큰글씨×좁은 폭에서만. 더 줄이면 뜻이 흐려진다(예: '사고 기록이 없어'는 '사고가 없다'로 읽힌다). 근본 처방은 공용 gloss 가 아래 공간이 모자라면 위로 열리는 것 — DES 티켓으로 분리.

## 추가 — 마지막 손질: 말풍선 셋째 문장 (design-critic 고칠 것 1 · Steward 확정, 01:54~02:11)
- 문구: `'이력 미확인'은 사고 기록을 확인하지 못했다는 뜻이에요. 사고차인지 아닌지 모르니, 가격은 사고차로 가정해 계산합니다.` — detail.html 4a94bb53 → **ef6a8a24**, test_rec15_frontend 4de3cacc → **23832c5f**(첫·둘째 문안이 남지 않는다 단언), test_rec1_floor_view 0539de3b → **63db164a**('물건정보' g90_1 → 0c089eb4, sm6_1 → 7b7b5b64, 두 곳만 지우면 REC-15 이전 fb500dcd·81728f90), report.html e4508e49·app.css d1109243 그대로. 템플릿 주석에 새 뜻과 바꾼 이유(규칙 8).
- 관련 7파일 192 passed · 전체 스위트 **2,978 passed · 5 xfailed · 0 failed · 0 skipped**(자정 안 넘김, 가드 0, 노드 2,983) · 렌더 대조(재산정 10-01 사본): 다른 쪽 = 모든 상세 3,174, 문장을 가리면 같음, 리포트·그 밖 0 · popcheck 보통 390 148px 넘침 0 · 큰글씨 320 266px 넘침 36px(수용분 그대로) · 큰글씨 360 넘침 0 · 캡처 `after3/` N390 90f6a277 → bb3da8f3 · L320 7aef208f → e566fb95, Read 잘림 없음 · HEAD.txt b75ae0e2.
- **Steward 재현(02:20)**: 배포 단위 md5(detail ef6a8a24 · report e4508e49 · service f21990a0 · calculator 4507f450 · maint 01d53178 · app.css d1109243 · test_rec15_frontend 23832c5f · test_rec1_floor_view 63db164a) 일치, 관련 11파일 305 passed, `after3/d50904-accpop-N390` Read — 앰버 '이력 미확인' 칩 옆 말풍선에 새 문장.
