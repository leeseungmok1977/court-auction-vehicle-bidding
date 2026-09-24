# PANEL-56 4회차 — 면책 끝 문장의 빨간 굵기를 시세 없는 분기에서만 해제 (지시서 2026-09-24-14)

- 담당: frontend-engineer · 근거: 오너 결정 2026-09-24(문장은 그대로, 시세 없는 분기에서만 굵기·빨강을 뺀다) · 지적 원문: `reports/2026-09-24-panel56-cross-review.md` 항목 2(두 검수자 공통).
- 기준 커밋: 작업 시작·종료 모두 HEAD `3170098`(작업 중 커밋 없음). 캡처 `HEAD` 파일 = `3170098`, `TEMPLATE_MD5` 파일 = 작업트리 `report.html` md5 `58bc047a`(미커밋). 변경 **전** `report.html` md5 `84302824`.
- 손댄 파일(2): `web/templates/report.html` · `tests/test_panel55_report_nomarket_copy.py`. **커밋하지 않았다. 배포하지 않았다. 라이브로 요청을 보내지 않았다. 운영 DB 에 쓰지 않았다**(캡처는 스크래치 사본, 테스트는 tmp DB, 실물 조회는 `sqlite3 mode=ro`).
- 손대지 않은 것: 면책 본문 어휘(한 글자도 — 테스트가 바이트로 검사) · `app.css`(`npm run build:css` 전후 md5 **`bcfe1da6…` 동일**, 새 클래스 없음) · `service.py` · `detail.html` · 다른 판정.
- ⚠ 작업트리에 **내 것이 아닌** 변경이 같이 있다(사실, mtime 10:49~10:58 — 내 첫 편집 10:54 와 겹침): `tools/capture_store_shots.py`(M) · `tests/test_store_shot_tool.py`(M) · `tests/test_store_final.py`(??) · `tools/store_final.py`(??). 열지도 고치지도 않았다. **후 테스트 수에 이 파일들의 케이스가 섞인다**(§2 에서 분리).

## 1. 바꾼 것 (앵커 — 줄 번호 없음)

### `report.html` — 앵커 `권장가는 무효입니다`
변경 전:
```
… 대체하지 않습니다. <b style="color:var(--red)">입찰 중단 기준에 해당하는 사실을 미리 발견하면 권장가는 무효입니다.</b>
```
변경 후:
```
… 대체하지 않습니다. {% if report %}<b style="color:var(--red)">{% endif %}입찰 중단 기준에 해당하는 사실을 미리 발견하면 권장가는 무효입니다.{% if report %}</b>{% endif %}
```
- 술어는 본문(01~12)을 가르는 바로 그 `{% if report %}`(그 `{% else %}` 가지에 `sec-empty` 안내 그릇이 있다). 새 판정·새 변수·새 클래스 없음.
- 문장은 **한 번만** 적혀 있고 태그 여닫이만 감쌌다 → 두 분기의 문장 텍스트가 구조적으로 바이트 동일(복제본이 따로 놀 수 없다).
- `<div class="disc">` 위에 Jinja 주석 4줄(`{# PANEL-56 4회차 … #}`) — 그릇 안 바이트는 게이트 외 불변. CRLF 1678→1682 / bare LF 0 유지.
- 렌더(실측, 스크래치 서버 · `measure.json`):
  - 시세 없는 물건(`2025타경56677_1`, 공개 390·320 / 관리자 390): 문장이 `.disc` 텍스트 노드에 직접 — 부모 `DIV`, 색 `rgb(75,90,115)`(`--ink-soft`), 굵기 400, 11.5px. `.disc` 안 `<b>` 는 제목 `이용 안내 및 면책` 하나(`--ink`). 빨강 0.
  - 시세 있는 물건(`2026타경50403_1`, 공개 390): 문장이 `<b style="color:var(--red)">` 안 — `rgb(190,42,47)`, 700. **변경 전과 동일.**
- 대비(WCAG 공식 계산값, 측정 아님): 문장이 물려받는 `--ink-soft` #4B5A73 / `.disc` 배경 #EEF1F5 = **6.2:1**(≥4.5). 변경 전 그 문장 색 `--red` #BE2A2F 는 5.2:1 이었다 — 대비는 오히려 오르고, 채도·굵기만 빠진다.

### `tests/test_panel55_report_nomarket_copy.py` — 4회차 절 추가(파일 25→36 케이스)
- `import hashlib` · 픽스처에 `priced_1`(test_panel56 의 정의와 동일, 시세 13,000,000) 추가 — 기존 테스트는 id 로만 조회하므로 영향 없음(25 케이스 그대로 통과).
- 상수: `_DISC_OPEN` · `_DISC_LAST`(문장 원문) · `_RED_B` · `_PRICED_DISC_MD5 = 0aaec683ae6614f938f8c14f13627e2b`(**변경 전** 렌더에서 잰 값 — 스크래치 스크립트로 priced_1 공개·관리자 둘 다 같은 값, 367자, 편집 전에 측정).
- (a) `test_disc_last_sentence_is_plain_when_there_is_no_report` — nomed_1·nomed_flood·nomed_nostart × 공개·관리자 **6케이스**: 문장 1회 존재 · `var(--red)` 부재 · 문장이 앞 문장 뒤에 태그 없이 이어져 `</div>` 로 끝남 · 굵은 태그는 제목 하나(`<br>` 은 세지 않는다 — 첫 실행에서 `<b` 로 세어 `<br>` 이 걸렸던 것을 고쳤다).
- (b) `test_disc_unchanged_byte_for_byte_when_priced` — 공개·관리자: `.disc` md5 == 변경 전 값, 빨간 태그 안 문장 존재.
- `test_disc_differs_only_by_the_red_tag` — `unpriced == priced.replace(RED_B+문장+</b>, 문장)` : 두 분기는 태그 유무만 다르다.
- `test_disc_gate_uses_the_body_predicate_and_writes_the_sentence_once` — 원문: 문장이 소스에 1회 · 게이트 문자열 정확히 일치 · `.disc` 블록의 `{% if` 는 `[expected.acc, report, report]` 셋뿐 · `is_admin`/`bid_state(`/`_stop0`/`_tone0`/`median` 부재 · 본문 `{% if report %}` 의 `{% else %}` 가지에 안내 그릇이 있음.
- `test_priced_fixture_actually_renders_the_body` — 공허 통과 방지(priced_1 에 `sec-no` 있음, 안내 앵커 없음).
- 모듈 docstring 에 4회차 문단(처방·반증) 추가.

## 2. 테스트 — 전/후 · 반증

| | 결과 | 조건 |
|---|---|---|
| 전 | **1267 passed** | 편집 전 작업트리(HEAD `3170098`, 지시서의 1267 과 일치), `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`, 9분 48초 |
| 후 | **1296 passed, 2 failed**(수집 1298) | 같은 조건, 편집 완료 후, 4분 46초. ⚠ 같은 시각 다른 담당이 `tests/test_store_final.py`(신규)·`tests/test_store_shot_tool.py`(수정)를 넣고 있어 그 케이스가 섞인다 — §5 에서 분리 |
| 대상 파일 단독 | **36 passed** (25 → 36, +11 = 1+6+2+1+1) | `tests/test_panel55_report_nomarket_copy.py`, 27.8초 |

내 변경의 기대 델타는 **+11** 이다. 후 전체 수 − 1267 − 11 = 남의 것.

**반증(확인된 사실, 바이트 백업 → 복원 → md5 대조):** 두 `{% if report %}…{% endif %}` 를 지워 무조건 `<b style="color:var(--red)">…</b>` 로 되돌림(md5 `b36d8d49`) → 대상 파일 **8 failed / 28 passed** — `test_disc_last_sentence_is_plain_when_there_is_no_report` 6케이스 · `test_disc_differs_only_by_the_red_tag` · `test_disc_gate_uses_the_body_predicate_and_writes_the_sentence_once`. (b) 의 md5 테스트는 게이트가 없어도 통과한다 — 시세 있는 쪽은 원래 그 모양이니 맞다. 복원 후 md5 **`58bc047a`**(편집본과 동일), CRLF 1682 / bare LF 0.
※ 첫 반증 실행은 콘솔 cp949 인코딩으로 출력 단계에서 죽어 템플릿이 게이트 없는 상태로 남았었다 — `cp` 로 백업 복원, md5 대조 뒤 `PYTHONIOENCODING=utf-8` 로 재실행. 이 사이 다른 측정은 없었다(캡처는 그 뒤).

## 3. CSS
`npm run build:css` 실행(5.8초) → `web/static/app.css` md5 **`bcfe1da650e1bc197c0871e379277c77` 전후 동일**. 새 클래스·새 규칙 없음(변경은 Jinja 태그뿐).

## 4. 캡처 — `screenshots/panel56d/` (HEAD `3170098`, 작업트리 report.html md5 `58bc047a`)

조건: 로컬 uvicorn `127.0.0.1:8797` · `DATA_DIR`=스크래치 사본(auction.db + `2025타경56677_1`·`2026타경50403_1` 폴더) · `NC_NO_SCHEDULER=1`·`NC_NO_BACKGROUND=1` · 공개=`X-Forwarded-For: 203.0.113.9` · 관리자=헤더 없음 · Chromium DPR2 · 높이 844. **11개 png md5 전부 상이**(`md5sum … | uniq -d` 0건, `measure.json` 에 앞 8자리). 대상 물건이 실제로 그 분기를 타는지: `56677_1` 은 median NULL·기일 2026-08-18(`sqlite3 mode=ro` 로 확인) → `sec-no` 0 · 알약 `매각 종료`; `50403_1` 은 median 4,995,000·신뢰도 81 → 본문 01~12 렌더.

| 파일 | md5 | 확인한 것 |
|---|---|---|
| `public-pastdue-390` / `-full` / `-disc` | `fd8fc0ec` / `0b2d1b2a` / `1f3b6f49` | 문장 일반 글자(회색 400) — `-disc` 를 Read 로 열어 눈으로 확인. `.disc` y 665, 350×216, 문서 높이 1016 |
| `public-pastdue-320` / `-full` / `-disc` | `541c9b7e` / `99bbb1c7` / `5abacf59` | 같음. `.disc` y 764, 280×275. 뷰포트 샷에는 `.disc` 가 잘려 `-full`·`-disc` 로 본다 |
| `admin-pastdue-390` / `-disc` | `8512b99c` / `0fa89c2e` | 관리자도 같은 일반 글자(게이트는 `report` 이지 `is_admin` 이 아니다) |
| `public-priced-390` / `-full` / `-disc` | `1d69468e` / `1ce83890` / `846ffabe` | 빨간 굵은 문장 **그대로**(`(±8.6%)` 는 스크래치 DB 의 실측 MAE). `.disc` y 9031 |

- 기계 측정(6폭 × 2물건, DPR1): `pastdue` 320·360·390·430·768·1440 **가로 스크롤 0 · 화면 밖 요소 0**. `priced` 390·430·768·1440 도 0. **`priced` 320·360 은 scrollWidth +91px**(320: 411, 360: 451).
  - 이것이 이번 변경과 무관함을 **변경 전 템플릿으로 재현**했다(`diag_overflow`: 원본 `84302824` 로 바이트 교체 → 같은 서버·같은 측정 → 복원 md5 `58bc047a` 대조): 원본에서도 320 은 3회 중 2회 411, 360 은 3회 중 3회 451. 넘치는 요소는 `.disc` 가 아니라 **섹션 탭의 `<a href="#sec12">낙찰 절차</a>`**(right 326 @320). 전 회차(`panel56-round3.md` §4)가 "간헐 +91px, 재현성 미확인"이라 적은 그것이다 — 이번엔 **원인 요소까지 특정**(사실). 고치지 않았다(지시 범위 밖·`.disc` 와 무관).
- 눈으로 본 것(Read): 390 `-disc` 공개·관리자, 320 `-disc`, 320 `-full`, 390 뷰포트, priced 390 `-disc`. 시세 없는 페이지에서 채도 있는 글자는 마스트헤드(남색)와 `PDF 저장` 버튼뿐이고 면책은 통째로 한 색이다. priced 는 빨간 굵은 두 줄이 전과 같다.

## 5. 후 테스트 전체 수 — 1298 수집 = 1267 + 내 것 11 + 남의 것 20 (딱 맞는다)

- **1296 passed, 2 failed** (`NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1 python -m pytest -q -p no:cacheprovider`, 4분 46초).
- 남의 것 20(사실, `--collect-only` 실측): `tests/test_store_final.py` **19 수집**(untracked 신규) + `tests/test_store_shot_tool.py` **22 수집**(HEAD 원문은 `def test_` 21개 → +1). 19 + 1 = 20.
- **2 failed 는 둘 다 `tests/test_store_final.py`** (`test_d_main_…_ast` · `test_e_…`) — `tools/store_final.py`(untracked, 다른 담당이 쓰는 중) 를 검사하는 파일이다. 내 변경(`report.html` 면책 게이트·`test_panel55…`)과 접점이 없다. 열지도 고치지도 않았다 — 그 담당의 진행 중 상태로 본다(**미검증**: 그 파일이 완성되면 어떻게 되는지는 내가 모른다).
- 내 대상 파일 단독: **36 passed**(25→36). 내 변경으로 실패한 테스트 **0**.

## 6. 못 한 것 · 확신 없는 것
- **라이브 미검증(사실)** — 로컬 사본 렌더. 배포 뒤 `/vehicle/2025타경56677_1/report` 를 XFF 로 보고 면책 끝 문장이 일반 글자인지, 시세 있는 물건은 빨간 굵은 문장이 그대로인지 봐야 한다. 배포는 지시서대로 하지 않았다.
- **PDF(인쇄) 미캡처** — 게이트는 태그 유무뿐이라 인쇄 CSS 에 새 규칙이 없고 `.disc` 인쇄 규칙도 손대지 않았다. 인쇄 렌더는 찍지 않았다(추정: 화면과 같다).
- **priced 320·360 의 +91px 가로 스크롤(사실, 변경 전에도 재현)** — 원인 요소 `<a href="#sec12">낙찰 절차</a>`(섹션 탭). 이번 범위 밖이라 두었다. 티켓이 없으면 하나 필요하다(간헐 재현: 320 은 3회 중 2회).
- **줄끝(사실)** — `tests/test_panel55…` 는 손대기 전에도 LF(CRLF 0 / bare LF 317)였고 LF 로 유지(405). `git status` 의 "LF will be replaced by CRLF" 경고는 전 회차와 같은 기존 어긋남. `report.html` 은 CRLF 1682 / bare LF 0.
- **첫 반증 실행의 cp949 사고(사실)** — §2 참조. 게이트 없는 템플릿이 남아 있던 시간에 다른 측정은 하지 않았고, 복원 md5 를 대조했다.
