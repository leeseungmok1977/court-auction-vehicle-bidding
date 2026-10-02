---
order: 2026-10-03-04
from: design-critic
ticket: AUD-17
result: done
verified: 재현
handoff:
  - to: frontend-engineer
    why: "AUD-17 관리자 문자열 3건 — 본 보고 §2 ①범례 낱말(skipped 경계 시각·detail-mismatch·실행 기록 '보류' 연결) ②불일치 안내(받은 상세 기준 표지·기존 값 그대로·관리자 전용 기록 링크) ③범례 dl.legend+keep-all·조치 칸 nowrap — 각 항 끝의 완료 기준대로. ⚠ ② 의 안내 상자는 SEC-1(공개 화면에서 ?an= 을 그리지 않음 — Steward 수정, 이 보고 끝 'Steward 재현' 절)이 먼저 들어간 위에서 작업"
---

# AUD-17 관리자 화면 바뀐 문자열 검수 (지시서 2026-10-03-04 · design-critic)

> Steward 옮김(2026-10-03 01:1x): 담당은 파일을 쓰지 못해 본문을 인계 메시지로 보냈다. 판정·고칠 것·완료 기준은 담당 문장 그대로, 근거 서술은 요지. 끝에 **Steward 재현** 절을 붙였다(운영 규칙 5).

## [요약]
되돌릴 것 없음 — 배포 유지. 새 문자열은 코드와 대조해 사실과 맞고 화면 넘침도 늘리지 않았다. 다만 운영자가 **뜻을 거꾸로 읽거나 엉뚱한 줄로 갈 수 있는 곳 세 군데**: ① 범례 skipped 의 날짜 경계("2026-10-02 전")가 바로 아래 표의 `2026-10-02 06:31 skipped` 행과 모순되고, 실행 기록의 '보류'를 범례에서 찾으면 다른 조치(quarantined)로 이어진다 ② 안내의 "매각물건 4≠3"은 어느 쪽이 이 물건인지 말하지 않는다(같은 화면 제목 줄은 "물건 4") ③ 범례가 한 문단이라 단어 중간 줄바꿈 5곳, 표의 코드가 하이픈에서 갈린다.

## 0. 본 것과 조건 (요지)
- 캡처를 Read 로 직접 열어 파일명 = 화면 확인: `screenshots/aud18-qa/`(anomalies before/after 1440·390 + 요소 4, vehicle-an before/after 1440·390 + 안내 요소 2 — 다시 찍은 before 2장은 스플래시가 아니라 실제 상세) · `screenshots/aud02-qa/`(범례·상단 1440 4장).
- 기준: aud18 `BASELINE.txt`(before = HEAD :8041, after = 수정본 :8042, 같은 DB 사본) · aud02 `HEAD.txt`(9c3374c). 교차: aud18 before 범례 md5 `64180019…` = aud02 after 범례 → 기준이 이어진다. md5 는 qa 기록 인용(재계산 안 함), 전후 차이는 육안 확인.
- 코드(읽기만): `web/app.py`(`admin_anomalies`·`analyze_one`·`vehicle_detail`) · `detail.html` `{% if an_msg %}` · `web/service.py`(`analyze_single`·`_log_detail_mismatch`·실행 기록 조각) · `detail_parser.detail_identity` · changelog. 라이브 접속 없음.

## 1. 배포 가능 여부 — 유지(되돌릴 사유 없음)
- 범례 4줄: `_require_admin` 뒤, 글자만 더함. 390 scrollWidth before 476 = after 476(표 폭, 기존). 1440 두 줄 그대로, 390 5 → 8줄·단어 중간 줄바꿈 2 → 4곳(후퇴, 작음).
- 안내 1종: 두 주장이 코드와 맞다 — '저장하지 않았습니다'(`analyze_single` 의 `except DetailMismatch` 가 행·상태 그대로) · '기록에 남겼습니다'(`_log_detail_mismatch(…, "단건 분석")`). 1440·390 단어 중간 줄바꿈 0. 예전엔 같은 단건 분석이 남의 상세를 **조용히 저장**했다(qa N2) — 지금은 거절하고 말한다. 화면 관점의 가장 큰 개선.
- 남은 것은 읽기·뜻의 문제이지 값·판정 오류가 아니다.

## 2. 고칠 것 3건 (우선순위순 · AUD-17 · frontend)

### ① [/admin/anomalies 범례] skipped·detail-mismatch 낱말 — 날짜 경계 모순, '보류' 끊김, 코드 주석 말
현재: `skipped=다른 법원 충돌로 반영 안 함(2026-10-02 전 기록·마지막 방어선)` · `detail-mismatch=받은 법원 상세가 보낸 키의 물건이 아님 — 저장 안 함(기존 행 유지)`.
문제(확인): ⑴ 범례는 "10-02 **전** 기록"인데 아래 표에 `2026-10-02 06:31:24~35 … skipped` 10여 행 — 경계는 날짜가 아니라 **배포 시각**(17:16). 글자대로 읽으면 오경보, '범례가 틀렸네' 습관이 붙으면 진짜 새 skipped 를 놓친다 ⑵ 실행 기록은 세 조치를 모두 '보류'로 적는다(`검토 재확인 N(복원 N·보류 N)` = quarantined · `⚠사건번호 충돌 N 보류` = skipped · `⚠상세 불일치 N 보류` = detail-mismatch) — 범례에서 '보류'가 든 줄은 `quarantined=등록 보류(숨김)` 하나뿐 ⑶ '마지막 방어선'·'보낸 키'는 코드 주석 말, 새로 생기면 무엇을 하는지가 없다(주석엔 '정상이면 0').
목표 낱말: `skipped` → `사건번호 충돌로 반영 안 함(물건 누락). 2026-10-02 17:16 배포 전 기록 — 그 뒤로는 0 이 정상, 새로 생기면 확인. 실행 기록 '⚠사건번호 충돌 N 보류'` · `detail-mismatch` → `상세 불일치 — 법원 상세가 이 물건과 달라 저장 안 함(기존 값 유지). 0 이 정상. 실행 기록 '⚠상세 불일치 N 보류'`. 나머지 5줄 그대로. 사유 칸 `DETAIL_MISMATCH_REASON` 은 **바꾸지 않는다**(쌓인 행과 갈림). 17:16 은 Steward 가 서버 시각 확인(→ 아래 Steward 재현: 확인됨).
**완료 기준**: 범례에서 '보류'로 찾으면 quarantined·skipped·detail-mismatch 세 줄이 모두 걸린다 · 경계 표기와 표의 skipped 행 시각이 모순되지 않는다.

### ② [/vehicle/{id}?an= 불일치 안내] "4≠3"의 방향, 값 상태, 기록으로 가는 길
현재: "법원 상세가 이 물건과 달라 저장하지 않았습니다(매각물건 4≠3, 목적물 4 없음). 관리자 무결성 검토 기록에 남겼습니다."
문제: ⑴ (확인) `detail_identity` 는 `매각물건 {받은}≠{이 물건}` 순, 제목 줄 "물건 4"는 item_no(목적물) — 숫자 4가 세 번 나오는데 매각물건 4 만 남의 것. 거꾸로 읽기 쉽다(추정 — 사람 관찰 없음) ⑵ (확인) 행·상태 그대로인데 안내는 말하지 않는다(범례는 '기존 행 유지') ⑶ 기록 위치를 이름으로만 — 같은 화면 아래 보라 '이 물건 분석(약 10초)' 단추가 다시 누르라고 부른다(같은 키면 같은 결과일 가능성 — 추정·미검증).
목표: 문구 `법원 상세가 이 물건과 달라 저장하지 않았습니다(받은 상세 기준: 매각물건 4≠3, 목적물 4 없음). 기존 값은 그대로입니다.` — 앞 구절은 한 글자도 바꾸지 않는다(`tests/test_aud18_detail_key.py` 가 검사), '받은 상세 기준:'은 `analyze_one` 에서 안내를 만들 때만, reasons 문자열(감사기록 메모와 공유)은 그대로((확인) '≠'는 사건·법원·매각물건 세 곳 모두 받은 값이 왼쪽). 기록 링크 `무결성 검토 기록 열기 →`(`/admin/anomalies`)를 상자 안 별도 `<a>` 로, **관리자일 때만**. '다시 분석해도 같은 결과'류 문장은 backend 확인 전 넣지 않는다.
**완료 기준**: 1440·390 단어 중간 줄바꿈 0 유지 · 기존 테스트 통과 · 비관리자 화면에 /admin 링크 0.

### ③ [/admin/anomalies 범례 모양] 한 문단 → 코드별 한 줄, 키 굵기를 표 조치 칸과 같게, keep-all, 조치 칸 nowrap
현재(확인): `<p>` 하나에 뒤로가기 링크 + 코드 7개, 구분자 ', '(앞 3)·' · '(뒤 4)이고 '·'는 설명 안에도 있다 · 범례 키 굵기 400 vs 표 조치 칸 600 · 단어 중간 줄바꿈 1440 '마지/막', 390 '등/록'·'법원/의'·'유/지'·'갱신/에' · 표 조치 칸이 하이픈에서 갈림('detail-/mismatch' aud18 1440·390, 'stored-/as' aud02 1440).
목표(`admin_anomalies` 의 `<style>` 과 범례 마크업):
```html
<p><a href='/admin'>← 관리자</a></p>
<dl class='legend'>
  <dt>resolved</dt><dd>재확인 후 복원</dd>
  <dt>quarantined</dt><dd>등록 보류(숨김)</dd>
  <dt>error</dt><dd>재조회 오류</dd>
  <dt>stored-as</dt><dd>다른 법원의 같은 사건번호 — 법원 구분 id 로 따로 저장(기존 행 유지)</dd>
  <dt>skipped</dt><dd>(① 낱말)</dd>
  <dt>detail-mismatch</dt><dd>(① 낱말)</dd>
  <dt>requeued</dt><dd>상세 조회 키 정정으로 다음 매일 갱신에 다시 받기 예약</dd>
</dl>
```
```css
.legend{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;margin:0 0 12px;word-break:keep-all}
.legend dt{font-weight:600}
.legend dd{margin:0}
td:nth-child(3){font-weight:600;white-space:nowrap}   /* 기존 규칙에 nowrap 만 더함 */
```
효과: keep-all 로 낱말이 통째로 넘어가고, dt 600 = 조치 칸 600 으로 표와 범례의 코드가 같은 모양, 구분자 문제는 구조로 사라짐. 색은 넣지 않는다(빨강 남발 전례). 비용(추정): 1440 범례 34px → 약 130px, 390 은 nowrap 으로 조치 칸 30~40px 넓어질 수 있음(관리자는 SSH 터널 PC). 최소안: 범례 `<p>` 에 keep-all, 키 `<b>`, 조치 칸 nowrap. 선택: 코드가 쓰는 action 7종(`record_anomaly` resolved·quarantined·error · `_log_anomaly` stored-as·skipped·detail-mismatch·requeued)이 범례 `<dt>` 에 다 있는지 보는 테스트 1개.
**완료 기준**: qa 와 같은 측정(글자별 줄 위치)으로 1440·390 범례 `mid: true` 0 · 표 조치 칸 코드 한 줄 · 390 scrollWidth 변화 기록.

## 3. 잘된 점 (요지)
범례가 코드가 쓰는 action 7종을 빠짐없이 덮는다(호출 전수 대조 — A-01 '버린 기록이 관리자 화면에만 남아 14일간 아무도 몰랐다'의 교훈 실행) · 새 4줄 모두 데이터가 어떻게 됐는지 적었다('기존 행 유지'·'저장 안 함'·'다시 받기 예약' — requeued 는 언제 풀리는지까지) · 새 줄이 기존 범례와 같은 요소·스타일(13px·400·기본 검정), 새 시각 어휘 없음 · 안내는 결과 → 근거 → 기록 위치 순, 기록 이름이 페이지 제목·/admin 링크와 같고, 보호를 위한 거절에 빨강이 아니라 앰버 · 감사기록 메모는 보냄/받음을 다 적되 차대번호·등록번호는 적지 않는다.

## 4. 물어본 것에 대한 짧은 답
크기·색·굵기 — 새 줄과 기존 범례는 같다, 어긋남은 범례(400·13px)와 표(600·16px — 쿼크 모드 §5-b) 사이 → ③ · 색 — 범례 무색·안내 앰버 맞다 · 낱말 — stored-as·requeued 는 서고, skipped·detail-mismatch 는 운영자 말이 아니고 '보류'와 안 이어진다 → ① · 다음 할 일 — 절반(무엇이·어디에는 말함, 값 안전·기록 링크·4≠3 방향 없음) → ②.

## 5. 범위 밖 관찰 — 티켓화는 Steward 판단(재현 필요)
- **a. `?an=` 문구가 공개 라우트에서 누구에게나 그려진다** — `vehicle_detail(request, vid, cc="", an="")` → `"an_msg": an` → `detail.html` `{% if an_msg %}` 앰버 상자, 관리자 확인 없음. 누구나 `/vehicle/{id}?an=<아무 문장>` 으로 공식 안내 상자 모양의 임의 문장을 띄울 수 있다(HTML 은 자동 이스케이프 — 글자만). AUD-18 전부터 있던 길(기존 '분석 실패…' 등). 코드 확인 · 라이브 미검증. 방향: 관리자에게만 그리거나, 정해진 코드(`an=mismatch` 등)만 받아 서버가 문구를 고르게.
- **b. `/admin/anomalies` 에 `<!DOCTYPE html>`·viewport 메타가 없다**(확인) — 쿼크 모드라 표가 body 13px 을 안 물려받고 16px, 실제 폰은 980px 배치 후 축소. qa 390 캡처는 데스크톱 좁은 창 조건으로 보임(추정). DOCTYPE 을 넣으면 표 글자가 16 → 13px 로 화면 전체가 달라지므로 별건.
- **c. 제목 옆 "· 200건"은 총계가 아니라 상한** — `db.list_anomalies(200)` 의 `len(rows)`. 실제 총계는 더 클 가능성(추정). '최근 200건'으로 쓰거나 총계를 함께.

## 6. 확인 / 추정 / 미검증 (요지)
확인: 새 범례 4줄 = 기존과 같은 요소·스타일 · 단어 중간 줄바꿈 5곳 · 조치 칸 하이픈 갈림 · skipped 경계 모순(배포 시각은 문서 기록 — 서버 미확인) · 실행 기록 '보류' 3조치 · '≠' 받은 값 왼쪽 · 제목 "물건 N" = item_no · 불일치 시 행·상태 그대로 · 쿼크 모드 16px. 추정: 4≠3 오독 가능성 · 다시 분석해도 같은 결과 · qa 390 = 데스크톱 모드. 코드 확인·라이브 미검증: `?an=` 공개 렌더. qa 인용: 캡처 md5.

---

## Steward 재현 (2026-10-03 01:0x~01:1x, 운영 규칙 5)
- **§5-a 라이브 재현됨** — `https://naechaget.duckdns.org/vehicle/2026타경52189_1?an=AN_REPRO_TEST_0103`(공개 경로, 로그인 없음) → 응답 HTML 의 `bg-amber-50 … info` 상자 안에 `AN_REPRO_TEST_0103` 이 그대로. `?cc=` 는 그려지지 않음(`cc_msg` 를 쓰는 템플릿 0). 안내를 만드는 `analyze_one` 은 `_require_admin` — 공개 화면엔 필요 없는 문장이다. → **SEC-1** 신설·수정: `vehicle_detail` 이 `"an_msg": an if _adm else ""`(같은 함수의 기존 `_adm = is_admin(request)`), 테스트 `tests/test_sec1_an_msg.py` 2개(공개 미렌더 · 관리자 렌더) — 수정 전 코드에서 공개 테스트 빨강 확인, 관련 62 passed. **배포는 오너 승인 대기**.
- ① 범례 문자열·실행 기록 '보류' 조각 3종·`detail_identity` 의 `{got}≠{want}` 순서·`vehicle_detail` 의 `an` 전달 — 코드에서 모두 담당 서술과 같음(grep).
- ① 의 배포 시각: AUD-02 서버 반영 = 서비스 재시작 `Oct 02 17:16:00 … Application startup complete`(Steward 가 배포 직후 journal 로 확인) — 목표 낱말의 '17:16' 은 맞다.
- §5-b·c 는 관리자 전용 — AUD-17 행에 함께 적는다(별건 처리 판단은 frontend 착수 때).
