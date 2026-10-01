---
order: 2026-10-01-04
from: frontend-engineer
ticket: REC-8
result: done
verified: 재현
handoff: []
---

# REC-8·REC-9·PLAY-1 화면 수정 — 진입점 6곳 · 폴링 KPI · 침수·전손 물건의 예상가/상한선 가리기 · /privacy 최종 문안 (지시서 2026-10-01-04)

> Steward 옮김(2026-10-01): 담당은 하네스 규칙상 파일을 쓰지 못해 본문을 인계 메시지로 보냈다. 아래는 그 본문의 요지와
> 발견·배포 메모를 담당 문장 그대로 옮긴 것이다. Steward 재현(같은 날): 템플릿의 `judgment=입찰 검토 가능` 링크 0 · base.html 의
> kpi-ok·kpi-wait 덮어쓰기 0 · /privacy 보호책임자 줄 1 · 구제 기관 번호 4개 · app.py `updated` = 2026-10-01.

> **기준**: HEAD ace878e 위의 작업 트리(시작 82d7312, 사이 web/·tests/·src/·config 변경 0). 커밋·배포·ssh·외부 요청 0. 운영 8765·data/ 무접촉.
> web/app.py·service.py·db.py 는 손대지 않았다(md5 deb9ea97·74de9b9b·577f595e = backend 보고서 값). config.yaml md5 5411eb7a. `npm run build:css` 결과 app.css md5 f901bb86 그대로.
> **바꾼 파일**: 템플릿 9개(_macros · base · dashboard · detail · landing · privacy · report · vehicles · watchlist), 기존 테스트 1개(test_ux2_ux5_nav_state — 검토 추천 칩 href 정규식 1줄), 새 테스트 3파일 43개(test_privacy_play1 9 · test_rec8_frontend 11 · test_rec9_frontend 23).

## [요약]
- **PLAY-1 /privacy**: compliance-review §13.2 ①~⑧ 반영. 테스트가 문서의 '교체 후' 인용문 40줄을 직접 읽어 렌더된 화면과 대조한다 — 40줄 모두 일치. ② ※ 문장은 정정안(A), ④ 채택, F3 안 함. 자동 수집 행은 바이트 그대로, 연락처는 `{{ contact }}`, 기관 링크 4곳 https. 절 번호 1~11, 개정 이력 5줄(마지막 줄 2026-10-01 = app.py `updated` — 테스트 고정). 개정 이력 마지막 줄 날짜는 고정 문자열(다음 개정 때 `updated` 를 올려도 이력이 거짓이 되지 않게).
- **REC-8**: ⑴ 진입점 6곳 href → `/vehicles?bucket=review&sort=expected`(글자 그대로). ⑵ base.html 폴링의 kpi-ok·kpi-wait 덮어쓰기 삭제(null 가드·fmt 유지). ⑶ 알림 '전체 N건 →' → `/vehicles?bucket=review&upcoming=3&sort=sale_date` — 알림과 같은 집합(픽스처 7=7, 합성 장면 9=9, 옛 링크는 67).
- **REC-9**: `no_estimate` 가 참이면 네 화면(detail 6 · report 10 · vehicles 3 · watchlist)에서 예상낙찰가·밴드·상한선과 그 값에 기댄 문장·계산을 그리지 않는다. 목록 밖 같은 원칙 7곳도 처리. 자리 표시는 큰 자리 '예상낙찰가 · 입찰 상한선' + '침수·전손 의심 — 내지 않습니다'(`ui.withheld` 매크로 한 곳), 좁은 칸 '내지 않음' + '침수·전손 의심'. report ② '이미 입찰 상한선을 넘습니다' → '침수·전손 의심이라 입찰 보류입니다'. 06·07·08·10 은 머리·번호를 남기고 회색 레일 `sec-empty` 한 줄. 판정 상자·칩·'입찰 중단 기준'·육각형·재판매 손익분기 산정표·정렬은 일부러 그대로.
- **테스트**: 전체 **2,748 passed · 5 xfailed**(656초, 실행 중 대상 파일 md5 불변). 새 테스트를 HEAD 템플릿에 대면 42개 중 35개 빨강(초록 7개는 전제·대조군·불변 확인), 43번째는 변이로 KILLED. 1차 실행에서 test_panel_r2_fixes 의 앵커 `{% if expected.basis %}` 를 편집이 깨뜨려 1 failed → 앵커를 되살려 2차 통과.
- **캡처**: `screenshots/rec8-9/` (before 57 · after 110 · HEAD.txt). 8개 화면 × 6폭(320·360·390·430·768·1440) 가로 스크롤 0, 화면 밖 요소 0. before/after 17쌍 md5 모두 다름. 알림 머리는 실데이터에 알림이 0건이라 합성 장면(d_alert — 숫자는 실제 물건 상태가 아님)으로 찍었다. 34408 네 화면을 Read 로 열어 확인(히어로·산정 근거·리포트 01·목록 카드·관심 화면).

## 6. 발견 — 고치지 않음 (범위 밖 · 판단 필요) — 담당 문장 그대로
1. 목록 lg 표와 관심 표의 '상한가(재판매)' 칸이 음수를 그대로 찍는다(34408: -13,321,000). REC-1 4회차가 리포트에서 막은 것과 같은 종류다.
2. 상세 '재판매 손익분기 산정'의 '= 손익분기 상한 -13,321,000'이 초록(emerald) 막대와 글자로 나온다. 음수에 '좋음' 색이다.
3. 리포트 01 육각형 '가격 메리트 100'(최저가÷시세)이 침수차에서 가장 긴 막대로 나온다. backend가 이미 '판단 필요'로 올린 항목이다.
4. 리포트 '입찰 중단 기준' 문장의 '본 리포트의 권장가는 즉시 무효' — no_estimate 물건에는 권장가가 없다.
5. 관심 화면에서 등급 flood이고 저장 판정이 '시세 신뢰도 낮음'인 물건(09-29 사본 5대)은 칩이 '신뢰도 낮음'인데 새 자리 표시는 '침수·전손 의심'이라 서로 다른 말을 한다. 칩 체계 통일은 KCAR-3 ② 소관이다.
6. 정렬: 목록·관심의 '예상낙찰가 높은순'과 '여유 큰 순'은 가린 값으로도 정렬한다. 서버 쪽이고 backend 명세대로 그대로 두었다.
7. 목록 lg 표의 '다음 기일 미정'이 mono 칸 안 한글이라 자간이 벌어진다. test_render_smoke 규칙이 Jinja 식 안의 리터럴을 보지 못한다.
8. 상세 히어로에 '침수·전손 의심'이 세 번(판정 상자 · 칩 · 자리 표시) 나온다. 지시 문구를 따른 결과다. 줄일지는 디자인 검수가 판단할 일이다.
9. 기존 주석의 줄 번호 포인터 여러 개가 HEAD에서 이미 어긋나 있다(app.py 'report.html:892·900', service.py 'report.html:563', landing 'report.html:212', report 'dashboard.html:421', watchlist 'vehicles.html:460-466', tests 'report.html:892·900·1075'·'detail.html:288·408'). 이번 편집이 정확하던 포인터를 새로 어긋나게 한 경우는 없다.

## 8. 배포·후속 메모 — 담당 문장 그대로
- **privacy.html은 app.py와 같은 커밋으로 나가야 한다**(§13.2-⑨). 템플릿만 나가면 머리는 '시행일 2026-09-11', 개정 이력 마지막 줄은 2026-10-01로 서로 다른 말을 한다. 배포가 10-01을 넘기면 두 값을 함께 바꾼다. 테스트가 두 값이 같은지 본다.
- **N1(A/B)은 오너 확인을 기다리는 중이다.** 바꿀 곳은 세 곳이다: privacy.html ※ 문장의 그 구절 · tests/test_privacy_play1.py 의 `N1_SENTENCE`·`N1_OTHER` · compliance-review §13.2-② 인용문.
- **REC-9는 서버(no_estimate)와 함께 나가야 닫힌다.** REC-8 진입점과 알림 링크는 HEAD 서버도 bucket·upcoming을 받으므로 단독으로 나가도 동작한다.
- **디자인 검수 권고**: 공개 화면이고 판정·숫자 표시를 바꾼 변경이라 app-design-expert와 design-critic 둘 다(교차검수) 대상이다. 특히 볼 것: §6-8(히어로의 '침수·전손 의심' 세 번 반복) · 리포트 `.v-held`의 무게 · 06·07·08·10을 회색 레일로 둔 선택 · §6-1~4.

## 7. 확인 · 추정 · 미검증 (요지)
- **확인**: §13.2 문안 40/40, 09-06·09-11 커밋, 진입점 href(소스·렌더·6폭), 폴링 덮어쓰기 0, 알림 링크 = 알림 집합, REC-9 네 화면 × 3 픽스처 금액 0·대조군 그대로, 34408 육안, 6폭 넘침 0, 빨강 35/42·변이 KILLED, 스위트 두 차례, backend·config md5 불변.
- **추정**: '내지 않음'이 '미산출'과 다르게 읽힐 것(사용자 검증 아님) · 템플릿만 먼저 배포돼도 오류 없음 · 재판매 기준선 가드의 실데이터 영향 0.
- **미검증**: 라이브 /privacy 의 `privacy_contact` 실제 값·http→https 301 · 기관 링크가 실제로 열리는지 · 실데이터 알림 7건 이상 장면 · 큰글씨·인쇄 · 실제 폰·TWA · `expected.source` 가드 · 디자인 에이전트 검수.
