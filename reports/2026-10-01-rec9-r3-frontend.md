---
order: 2026-10-01-20
from: frontend-engineer
ticket: REC-9
result: done
verified: 재현
handoff: []
---

# REC-9 3회차 화면 수정 (frontend-engineer, 지시서 2026-10-01-20)

> Steward 옮김(2026-10-01): 담당은 하네스 규칙상 reports/ 에 쓰지 못해 본문을 인계 메시지로 보냈다. 항목별 결과·발견은 담당 문장 요지, 수치는 그대로.
> **Steward 재현(같은 날)**: 바뀐 파일 md5 5개가 아래 표와 같음 · `tests/test_rec9_r3_frontend.py`·`test_rec9_r2_frontend.py`·`test_rec1_r4_view.py`·`test_rec9_frontend.py`·`test_privacy_play1.py` 134 passed · 캡처 4장 Read(12085 배너 N390 — "침수·전손 의심 물건이라 시세·입찰가를 내지 않습니다 — 입찰하지 마세요." · 12085 산정 근거 L320 — 로즈 보류 상자, '입찰하지 마세요.' 한 줄 · 사고 등급 `.stop` L320 — 태그 위·문장 아래 전폭, 잘림 없음 · 34408 01 요점3 새 문장) · `d12085-banner-N390` 전후 md5 d1d0839e/484890a3 다름.
> 기준: HEAD 8e8fc2e(작업 중 583bf61 로 이동 — docs·reports 만, web/·tests/·src/·config diff 0). 커밋·push·배포·ssh·외부 요청 0, 저장소 data/·8765 무접촉, app.py·service.py·db.py·config.yaml 무수정.

## [요약]
- A1~D 전부 반영. 12085 사본 상세: '입찰하지 마세요' 2회, "직접 확인하세요" 0, '아직 계산되지' 0, '다음 기일 예상 최저가' 0. 비침수 대조군(10300) 바이트 그대로.
- 전수 렌더 대조(css_v·B5 CSS 정규화 후): 09-29 사본 3,103쪽 중 14쪽, 10-01 사본 3,228쪽 중 10쪽 다름 — 전부 노린 쪽. 라이브(10-01) 대상: 상세 5쪽(12085·51723·93·50330·50782), 리포트 4쪽(B4), /privacy. B1~B3·C1·C2 는 10-01 사본 대상 0대, B5 CSS 는 모든 리포트.
- 테스트: 새 파일 42개 중 변경 단언 31개가 8e8fc2e 에서 31/31 빨강(대조군 10·불변 1 초록). 변이 22종 모두 KILLED(qa 생존 N14·N35·N36 포함). 전체 스위트 **2,853 passed · 5 xfailed · 0 failed · 0 skipped**(941초, 전역 가드 시도 0, 작업 트리 사본에서).
- 캡처 28쌍 중 22쌍 다름, 같은 6쌍은 전부 설계상 대조군. 6폭+큰글씨 26지점 × 전후 가로 넘침 0·화면 밖 0.

## 바꾼 파일 md5 (8e8fc2e → 작업 트리)
| 파일 | 전 | 후 |
|---|---|---|
| web/templates/detail.html | 8cabfb39 | 6ba93665 |
| web/templates/report.html | 83a74220 | 4d52fc52 |
| web/templates/vehicles.html | 0c5eb448 | 03b004dc |
| web/templates/watchlist.html | 7ba56c98 | 5226ba81 |
| web/templates/privacy.html | b2465d3e | 699f4726 |
| web/static/app.css | d1109243 | 같음(재빌드 출력 동일 — `whitespace-nowrap`·`bg-slate-400` 이미 빌드됨) |
| tests/test_rec9_r2_frontend.py · tests/test_rec1_r4_view.py | 수정 | |
| tests/test_rec9_r3_frontend.py | 새 파일(42개) | |

배포 단위: 템플릿 5 + 테스트 3(app.css 불변).

## 항목별 (요지)
- **A1** no_estimate 로즈 보류 상자를 산정 근거 카드 맨 앞 갈래로('분석 전'·nomarket·'시세 없음'보다 먼저), '입찰하지 마세요' `whitespace-nowrap`. 기존 갈래는 `v.judgment == '입찰 보류'` 만 남김 — **지금 닿는 물건 없음**(`_display_judgment` 가 낙찰을 '종결'로 바꾸므로 '입찰 보류'면 항상 no_estimate, 사본 저장 '입찰 보류' 1대·0대 → 그 1대도 no_estimate), 주석에 사실대로.
- **A2** 배너 Steward 문구 그대로, '아직'·'현재 … 상태입니다' 0, 수입·상용 안내는 `elif not can_analyze and not no_estimate`. 관리자 [이 물건 분석] 버튼 그대로(12085·10300 관리자 렌더 확인).
- **A3** `{% elif next_min and not floor_guard and not (bidst and bidst.no_estimate) %}` — 10-01 사본 12085(8,750,000)·50330(124,620,000)·50782(42,940,000) 행 빠짐.
- **B1** `_noest` li 교체, else `elif exp and not _noest` → `elif exp`(같은 값). **B2** 술어 `report.stop_active or _noest`, '(01)' 삭제, 주석 새 규칙으로, STOP_SENTENCE·KWFLOOD 기대값 갱신. **B3** class·글자 술어 둘 다(`v|accv` '무사고'는 REC-12 ⑷). **B4** "0원 이하 — 되팔이로 목표마진을 남길 낙찰가가 없습니다"(값 칸 그대로, 1470·50483·50644·12272 이 줄도 바뀜 — 의도).
- **B5** `.stop{flex-wrap:wrap;gap:8px 12px}` + `.stop p{flex:1 1 12em;min-width:0}` + `@media screen and (max-width:359px){html.nc-large .stop{padding-left:12px;padding-right:12px}}`(대체 서체에서 off 갈래 7줄 → 6줄). 설명은 Jinja 주석. 12 '지참' 상자도 같은 `.stop` 이라 큰글씨 320 에서 쌓임(152→220px, 9→5줄). 보통 320 이상·큰글씨 360 이상은 태그 옆 그대로.
- **C1** no_estimate 행 점 `bg-slate-400`(등급 무관). **C2** 목록 lg no_estimate 행 최저가 `text-mut`·title 없음, 관심 lg 표 `overfloor` 로즈+title 도 `and not v.no_estimate`.
- **D** privacy `<style>` 안 CSS 주석 → `{#- … #}`(렌더 0바이트). 같은 배치의 새 내부 메모(`<!-- -->`·`/* */`)는 이 1건뿐.
- **E1** 빌드 app.css 에 `ring-inset`·`ring-white/30`·`bg-white/[0.12]`·`sm:ml-auto`(640px 미디어 안)·`whitespace-nowrap`·`bg-slate-400` 규칙 + 템플릿 사용처 단언. **E2** 종결·0원 이하(CLNEG) 목록 lg 상한가 '—', 진행 중(OPNEG) '산정 불가'. **E3** 픽스처 FLLOW·FLPRE(시세 없는 침수) · FLOOD(34408형) · KWFLOOD·KWOVER(키워드 보류) · 대조군 ACC·LOW·POS·OKINS·MKTCTL·PRECTL·CLFL·OPNEG(예전 마크업 원문 단언).
- 노드 이름 변경 1: `test_리포트_입찰_중단_기준은_무조건_보류를_말한다[KWFLOOD-off]` → `[KWFLOOD-on]`. 노드 수 2,816 → 2,858(+42). 고친 기존 테스트 9개도 HEAD 에서 빨강(r2 7 · r1_r4 2).

## 캡처 — `screenshots/rec9-r3/`(before 28 · after 28 · cap3_*.json · HEAD.txt)
HEAD.txt: 기준 8e8fc2e(583bf61 이동), 바뀐 파일 전후 md5, 데이터 d1001 c3a96d28(=gz 73a16417) · d0929 44a3f8d3 · d0929s e557149f(20278 키워드 보류+보험이력, 12604 flood), 촬영 15:16:17~15:19:09, 쌍별 md5·이유. 서버 시각 고정 10-01 13:40·외부 연결 차단, 대기 networkidle → `document.fonts.ready` → 500ms, 크롭 요소+8px(고정 요소 겹침 0). 같은 6쌍: 10300 대조군 3장 · 목록 정상 행(4160) · `.stop` stop_active·off 보통 390 2장. before stop_active 큰글씨 320 은 "감지되었습니ㄷ" 잘림, after 4줄로 상자 안.

## 측정 (요지)
26지점 전후 넘침 0·화면 밖 0(1440 상세·목록은 폰 프레임 안). `.stop`(웹폰트/대체 서체): 큰글씨 320 문장 칸 70~98px·11~16줄 → 220px·4/4/6줄(대체 4/6/6), 상자 sw/cw stop_active 256/244 → 244/244 · 큰글씨 360 252px·3~4줄 · 보통 320 212px·3~4줄 · 보통 390·768·1440 전후 같음.

## 발견 — 범위 밖, 고치지 않음 (담당 문장 요지)
1. 상세 '사고판정' 칩이 근거 없는 등급 none 을 **초록 '이력 미확인'**으로 그린다(`d10300-info-N390`) — 리포트 09 가 5회차에 "미확인은 앰버"로 고친 바로 그 오독. 칩 class 가 `accident_grade` 만 본다.
2. A1 옛 '입찰 보류' 갈래는 닿지 않는 코드(남김 — 지울지 판단 거리).
3. 관심 **모바일 카드** 최저매각가 로즈(`overfloor`)는 no_estimate 행에도 남음(사본 해당 0대).
4. 목록 lg 시세 칸 숫자 로즈(`over_mkt`)도 no_estimate 행에 남음(사본 0대).
5. base.html 에 이번 배치가 넣은 JS `//` 내부 메모 2줄("KPI 실시간 — …", "⚠ … REC-8 ⑵ …")이 모든 공개 페이지 소스에 실린다(옮기면 모든 쪽 바이트가 바뀌어 둠).
6. 키워드 보류 리포트 09 칸 글자 '무사고'(`rKW20278-chip09`)는 REC-12 ⑷.
7. 측정 함정: 웹폰트 로드 전에 재면 태그 폭 130→136px·줄 수 증가 — 2회차 수치 일부가 그 상태였을 수 있다.

## 확인 · 추정 · 미검증 (요지)
확인: 전수 렌더 대조 2벌 × 2트리 + diff, 테스트(전체·빨강·변이), 캡처 md5·눈, 측정, 관리자 버튼, 서버 기동 시 템플릿 md5, gz md5 전후 동일, 저장소 data/ 19,657개 크기·mtime 같음(`auction.db-shm` 만 15초 간격 갱신 — 8765 등 다른 프로세스로 추정). 미검증: 실제 폰·TWA·인쇄, 배포 뒤 라이브, 키워드 보류·'높음' 침수 행은 합성·픽스처로만(실데이터 0대). 스크래치 `scratchpad/rec9r3_fe/`(hx · serve · cap3 · stopm · stopsum · sweep3 · cmpsweep · mut3 · suite · pbuild3 · edit_*).
