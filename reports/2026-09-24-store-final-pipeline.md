# 스토어 최종 산출 파이프라인 `tools/store_final.py` — 지시서 2026-09-24-15 (qa-engineer)

- **기준 커밋(HEAD)**: `3170098` — 작업 시작·끝에 `git rev-parse HEAD` 로 확인, 작업 중 이동 없음.
- 커밋·배포·운영 DB 쓰기·라이브 외부 요청 **없음**. 촬영은 실행하지 않았다(`--dry-run` 만).
- `screenshots/` 는 git 밖(이 PC 에만). `final/` 8장의 캡처 기준 커밋은 **장별로** `final/HEAD.json` 에 있다(아래 §3 표).
- ⚠ 이 체크아웃에 **다른 담당이 동시에 작업 중**이다: 시작 시 `git status` 가 clean 이었는데 끝에는
  `tests/test_panel55_report_nomarket_copy.py`·`web/templates/report.html`·`reports/2026-09-24-panel56-disc-gate.md`(지시서 -14, 면책 강조)
  가 변경돼 있다. **내 것이 아니다** — 손대지 않았고, 아래 테스트 수의 '후' 값에는 그쪽 추가분이 섞일 수 있다(§5 에 분리해 적음).

---

## 1. 요약

`docs/STORE_LISTING.md` §재촬영 절차 의 4단계(촬영 `--all` → `--audit` → 오버레이 → 오너에게)를 **한 명령**으로 잇는
`tools/store_final.py` 를 만들었다. 기준월·캡션·대상 물건이 **사람 손을 떠났다**:
기준월은 `screenshots/store/HEAD.json` 의 촬영 시각(가장 최근 장)에서 만들고, 캡션(alt text)은 `docs/STORE_LISTING.md`
"제출할 8장" 표를 **실행 시 읽어** 쓰며, 대상 물건은 `capture_store_shots.SUBMIT_TARGETS`(4·5번 G90 / 6·7번 SM6)가 든다.

`python tools/store_final.py --dry-run` → **종료코드 0**, `screenshots/store/final/` 에 8장(1080×1920·RGB·md5 전부 상이) +
`HEAD.json`(장별 원본 md5·커밋·촬영 시각) + `ALT_TEXT.txt`(8줄, 최대 27자). 8장을 전부 Read 로 열어 띠·카드·탭바를 확인했다.

**final/ 8장의 md5 가 이미 검수를 거친 `overlay-draft/`(3차 시안, round2) 8장과 완전히 같다** — 파이프라인이 사람이 손으로
만든 시안을 바이트 단위로 재생산한다는 뜻이다(§3).

테스트 **1267 → 후 값은 §5** (내 추가분 +20: 신규 19 + 갱신 파일 +1). 변이 시험 6종 전부 의도한 테스트가 잡았다(§6).

---

## 2. 만든 것 · 바꾼 것

| 파일 | 상태 | 내용 |
|---|---|---|
| `tools/store_final.py` | **신규** | (a) 촬영 `--all` 서브프로세스(`--dry-run` 이면 건너뜀) → (b) `--audit`(rc 1 이면 중단) → (c) `store_overlay.main()` B-1·띠 250·`--basis` 자동 → `final/NN__B1.png` → (d) `final/HEAD.json` → (e) `final/ALT_TEXT.txt` → (f) 규격·모드·md5 검사, 위반 시 rc 1 + 목록 |
| `tools/capture_store_shots.py` | 수정 | `SUBMIT_TARGETS = {"detail": "/vehicle/2025타경34553_1", "report": "/vehicle/2026타경3364_1"}` · `--hero-detail`/`--hero-report`/`--pick` · `set_hero(role, href)` · `resolve_target(role)` · `pick_hero_vehicle(pg, role)` — 지정 대상이 있으면 **요청 없이** 쓰고, 없을 때만 `_scan_pick()`(예전 탐색·`hero_scan.json` 캐시) 폴백 · `shoot_detail`/`shoot_slide5` → `"detail"`, `shoot_report`/`shoot_hexa` → `"report"` |
| `tests/test_store_final.py` | **신규** | 19개 — (a)~(e) + 합성 원본으로 파이프라인 끝까지(§5) |
| `tests/test_store_shot_tool.py` | 수정 | 인자 정규식이 `--hero-detail` 을 `--hero` 로 잘라 읽지 않게(`[a-z0-9-]`), `set_hero` 검사를 역할형으로, `SUBMIT_TARGETS`·폴백 테스트 1개 추가(21 → 22) |
| `reports/2026-09-24-store-final-pipeline.md` | 신규 | 이 문서 |

`tools/store_overlay.py`·`docs/STORE_LISTING.md` 는 **손대지 않았다.**

### 2.1 `store_final.py` 가 지키는 것

- **기준월을 손으로 적지 않는다.** `basis_from_manifest()` 가 8장의 `at` 중 가장 최근을 골라 `YYYY년 M월 기준`(앞자리 0 없음) 을 만든다.
  8장의 월이 갈리면 경고를 찍고 가장 최근 월을 쓴다. 한 장이라도 `at` 이 없으면 SystemExit — 지어내지 않는다.
- **캡션은 문서가 원천.** `listing_captions()` 가 `### 제출할 8장` 제목(앵커 문자열) 아래 표를 읽는다. 표가 1..8 아니면 SystemExit.
  표와 `store_overlay.CAPTIONS`(그림에 그리는 것)가 갈리면 **촬영조차 시작하지 않고** rc 1 — 스크린리더와 그림이 다른 말을 하면 안 된다.
- **alt text 는 확정본 그대로**(1번의 " — " 포함). 그림에서는 줄바꿈이 대시를 대신하지만(오너 승인 항목) 텍스트는 원문이다. 줄마다 140자 검사.
- **원본을 도구 밖에서 바꾸면 잡힌다.** 원본 실제 md5 ≠ `HEAD.json` 기록이면 "기준 커밋을 믿을 수 없다" 위반(PANEL-45).
- **지난 회차 산출을 먼저 지운다**(`_clear_previous`) — 실패한 회차가 옛 장과 새 장을 섞어 두면 그게 제출된다.
- 임포트 부작용 없음(stdout 재설정은 `main()` 안). 촬영·대조는 서브프로세스(촬영 도구는 임포트만 해도 stdout 을 감싸고 playwright 를 끌어온다).

---

## 3. `python tools/store_final.py --dry-run` 실행 결과 — **rc 0** (2회 실행, 결과 동일)

기준월: `'2026년 9월 기준'` ← 가장 최근 촬영 `2026-09-24T08:03:12+09:00`(08_detail_lower). 8장 모두 2026-09 라 경고 없음.

| # | final/ | 규격 | final md5 | 원본 md5 | 원본 커밋 | 촬영 시각 |
|---|---|---|---|---|---|---|
| 1 | `06_landing__B1.png` | 1080x1920 | `3bcf6bf9b753e90f3ad10dcc7b9f7998` | `f0c3db0d4d16…` | `7b78b2e` | 2026-09-24T01:49:40+09:00 |
| 2 | `01_home__B1.png` | 1080x1920 | `61c563e3f0feaf3e2df97d659eecbd62` | `55f36ece007f…` | `7b78b2e` | 2026-09-24T01:49:50+09:00 |
| 3 | `02_accuracy__B1.png` | 1080x1920 | `6b50393a6ea23b578be8234c9bc79fbc` | `a4ae5529beab…` | `7b78b2e` | 2026-09-24T01:49:59+09:00 |
| 4 | `07_detail__B1.png` | 1080x1920 | `f58280eb0b8b209927667f8091ec849e` | `443d52ece695…` | `b641f93` | 2026-09-24T08:03:02+09:00 |
| 5 | `08_detail_lower__B1.png` | 1080x1920 | `beb322f01f636df987917e66bee54ed4` | `4eda6f5d34ea…` | `b641f93` | 2026-09-24T08:03:12+09:00 |
| 6 | `09_report__B1.png` | 1080x1920 | `c607a4718e933231bd381b21583cb0f5` | `a85aa16ea3f4…` | `931a134` | 2026-09-24T07:16:04+09:00 |
| 7 | `10_report_lower__B1.png` | 1080x1920 | `53cef592d0f58771b501f39f47bf48c8` | `503b97dde514…` | `931a134` | 2026-09-24T07:26:13+09:00 |
| 8 | `05_calendar__B1.png` | 1080x1920 | `cb58dc85618bd4ce2794d4614dc7b85a` | `f04f88e7c771…` | `931a134` | 2026-09-24T07:12:34+09:00 |

- 8장 md5 전부 상이(원본 8장과도 상이). 모드 전부 RGB(알파 없음). 오버레이 자체 검사도 통과(캡션 ≤ 카드 폭 915px 전 장, 세트 공통 49px).
- **원본이 세 커밋에서 나왔다**(`7b78b2e`·`931a134`·`b641f93`) — `--audit` 가 PANEL-45 경고를 찍고, `final/HEAD.json` 이 장별로 적는다.
  `final/HEAD`(한 줄)는 오버레이를 만든 커밋(`3170098`)이고 `_meta.note` 가 그 뜻을 적어 둔다.
- **final/ 8장 md5 == `overlay-draft/` 8장 md5**(8/8 SAME, 확인 명령 `md5sum` 양쪽 대조). `overlay-draft/HEAD` 는 `d019cc4` — 3차 시안(재검수 ④-1 반영본)이다.
  같은 원본·같은 파라미터(B1·250·`2026년 9월 기준`)라 PNG 가 바이트까지 같다. 즉 파이프라인이 **검수받은 그 그림**을 낸다.
- `final/ALT_TEXT.txt`: 8줄 · LF · BOM 없음 · 길이 [27, 23, 17, 23, 17, 20, 26, 21] · 최대 **27자**(상한 140). 내용은 문서 표와 동일(테스트 `test_b_실제_final_ALT_TEXT_가_문서_표와_같다` 가 이 PC 에서 실제 파일을 대조).
- `final/` 에는 오버레이가 남기는 `metrics.json`·`HEAD`·`_fonts/`(Pretendard woff2→ttf 캐시)도 있다. `_fonts/` 는 리포에 들어가지 않는다(`screenshots/` .gitignore).

---

## 4. 8장 육안 확인 (Read 로 직접 열어 봄 — 파일명과 화면 일치)

| # | 파일 | 띠(캡션 흰색 / 기준월 크림) | 카드(둥근 모서리, 축소) | 하단 탭바 |
|---|---|---|---|---|
| 1 | 06_landing | 2줄("감으로 입찰하지 않습니다" / "데이터로 먼저 봅니다", 대시 없음) + 기준월 | 랜딩 상단(무료로 시작·히어로·1297/444/74%/±9.5%) | 없음 — 랜딩은 탭바가 없는 페이지(정상) |
| 2 | 01_home | 1줄 + 기준월 | 홈 히어로 "실제 낙찰 275건 · 전체 평균 오차 ±9.5%", 추천 카드(A5, 최저매각가 14,700,000 / AI 예상낙찰가 17,400,000) | 있음(홈 활성) |
| 3 | 02_accuracy | 1줄 + 기준월 | 지표 타일 4개 전부(±9.5% · 94% · 61% · 275건) | 있음 |
| 4 | 07_detail | 1줄 + 기준월 | G90 상세 — 감정가 29,000,000 · 당시 출시가 7,706~15,511만원 · 유찰횟수 2회 · 최저매각가 16,240,000 한 프레임 | 있음(차량목록 활성) |
| 5 | 08_detail_lower | 1줄 + 기준월 | AI 낙찰 예측 분석 카드 — 판정 `지금 사면 이득`, 입찰 상한선 27,600,000원, 산정 기준 줄 | 있음 |
| 6 | 09_report | 1줄 + 기준월 | SM6 리포트 상단 — 한줄 판정, 입찰 상한선 1,420만원, "이 유형(…128건) 실측 오차 ±10.0%" | 없음 — 리포트 페이지는 상단 도구모음(상세로·인쇄·큰글씨·되팔기 계산)만 있고 탭바가 없다(정상, 9/22 판과 같음) |
| 7 | 10_report_lower | 1줄(폭이 가장 넓은 캡션, 카드 안) + 기준월 | 종합 프로필 육각형 **6/6축 산출**, 축 이름 6개, 막대 6개 | 없음(리포트, 위와 같음) |
| 8 | 05_calendar | 1줄 + 기준월 | 2026년 9월 달력, **24일 강조**(촬영일), "지난달 낙찰 실적 · 2026년 8월 · **시세 확인** 100건" | 있음(경매달력 활성) |

- 번호판: 07_detail 의 G90 전면 브래킷은 비어 있다(원본 촬영 때 확인된 그대로). 01_home 의 A5 사진은 번호판이 읽히지 않는다. — 결함 아님(compliance §7).
- '준비 중'·'다시 분석' 등 금지 문구 없음(원본 촬영 도구 `no_forbidden()` 통과분이고, 눈으로도 없음).
- 원본은 이번에 다시 찍지 않았으므로 화면 속 수치(±9.5%·275건·달력 24일)는 **원본 촬영 시각**(01:49~08:03) 기준이다. 배포 뒤 실촬영에서 바뀐다.

---

## 5. 테스트

- **전**: `python -m pytest -q` → **1267 passed**, 352 warnings, 606s (작업 시작 시 baseline, HEAD `3170098`).
- **후**: `python -m pytest -q` → **1298 passed**, 366 warnings, **107s**(HEAD `3170098`, 최종 상태에서 실행. 전 baseline 이 606s 였던 것은 이 변경과 무관 — 같은 스위트가 이번엔 1분 47초).
  - 내 추가분: `tests/test_store_final.py` **19개 신규** + `tests/test_store_shot_tool.py` 21 → **22**(+1) = **+20**(두 파일 `--collect-only` 41개, HEAD 에선 21개).
  - 나머지 **+11 은 내 것이 아니다**: 다른 담당(지시서 -14)이 같은 체크아웃의 `tests/test_panel55_report_nomarket_copy.py` 를 17 → 22 함수(수집 36개)로 늘렸다. 1267 + 20 + 11 = 1298.
  - 실패 0 · 줄어든 테스트 0.
- 스토어 3파일 단독: `test_store_final.py` 19 passed(31s) · `test_store_shot_tool.py` 22 + `test_store_overlay.py` 7 = 29 passed(21s).
- 신규 테스트가 보는 것(파일 독스트링과 같다):
  - (a) `run_capture()` 호출이 `if not a.dry_run:` 안에만 있다(ast, 부모 노드 추적) · 실제 `main(["--dry-run", …])` 에서 촬영 함수가 불리면 AssertionError · dry-run 이 아니면 촬영을 먼저 부르고 실패(rc 1)하면 대조도 안 한다.
  - (b) 도구의 표 파서 == 테스트가 **따로 읽은** 문서 표 == `store_overlay.CAPTIONS` · 1번 캡션에 " — " 포함 · 합성 실행의 ALT_TEXT 8줄·LF·BOM 없음·≤140 · (이 PC) 실제 `final/ALT_TEXT.txt` == 문서 표 · 141자 줄은 위반.
  - (c) 코드 문자열(독스트링 제외)에 `\d{4}년 \d{1,2}월` 없음 · `run_overlay()` 의 `"--basis"` 다음 원소가 `Name` · `main()` 의 `basis` 가 `basis_from_manifest()` 에서만 나옴 · 함수값: 최근 월 선택·11월 표기·월 갈림 경고·tz 없는 기록 혼용·`at` 없으면 SystemExit · 합성 원본에 2028-07 한 장을 섞으면 그림 metrics·HEAD.json 이 `2028년 7월 기준` + 경고.
  - (d) `main()` 의 마지막 `return` 이 `1 if violations else 0`(ast, 줄 번호 최대) · `validate_finals` 가 위반을 내면 rc 1 · 원본 md5 ≠ HEAD.json 이면 rc 1 · `validate_finals` 가 규격(1080×1900)·모드(RGBA)·없음·중복을 전부 잡는다.
  - (e) `SUBMIT_TARGETS` 가 `detail`=G90 `2025타경34553_1`, `report`=SM6 `2026타경3364_1`, 두 값이 다름 · 촬영 함수 4개가 역할을 씀 · `pick_hero_vehicle` 본문에서 `resolve_target(` 이 `_scan_pick(` 보다 앞이고 그 사이에 `return hero` · `store_final.run_capture` 가 `--all --hero-detail --hero-report` 를 그대로 넘김.
- 파이프라인 테스트는 **합성 원본**(단색 1080×1920 8장 + HEAD.json)으로 tmp 에서 끝까지 돈다. 촬영·대조는 monkeypatch(외부 요청 0). 오버레이는 진짜 Pretendard 로 그린다.
- 속도: Pretendard woff2→ttf 변환이 **58초**(실측; 캐시 적중 0.2초, 합성 1장 0.8초)라 첫 판은 테스트 1개가 82.5초였다. 세션 스코프 `font_cache` 픽스처(이 PC 에 변환본이 있으면 복사, 없으면 한 번 변환) + `out/_fonts` 로 복사·mtime 갱신으로 **19개 31초**.

---

## 6. 변이 시험 (6종, 바이트 백업 → 변이 → 해당 테스트 → 바이트 복원, 복원은 `read_bytes()==backup` 로 확인)

| # | 변이 | 파일 | FAIL 한 테스트 | 결과 |
|---|---|---|---|---|
| ① | `main()` 의 `if not a.dry_run:` 가드 제거 → dry-run 에도 촬영 | `store_final.py` | `test_a_촬영_호출은_dry_run_가드_안에만_있다`, `test_a_dry_run_은_촬영을_부르지_않고_끝까지_간다` | 2 failed ✓ |
| ② | `basis = "2026년 9월 기준"` 으로 박음 | `store_final.py` | `test_c_코드에_YYYY년_M월_문자열이_없다`, `test_c_오버레이에_넘기는_basis_는_변수다`, `test_c_합성_원본의_촬영_월이_그림과_metrics_에_들어간다` | 3 failed ✓ |
| ③ | `return 1 if violations else 0` → `return 0` | `store_final.py` | `test_d_main_은_위반이_있으면_1_을_돌려준다_ast`, `test_d_검사_함수가_위반을_내면_main_이_1`, `test_d_원본_md5_가_HEAD_json_기록과_다르면_1` | 3 failed ✓ |
| ④ | `SUBMIT_TARGETS["report"]` 를 G90 으로(두 역할 같은 물건) | `capture_store_shots.py` | `test_e_SUBMIT_TARGETS_가_G90_과_SM6_를_역할별로_든다` | 1 failed ✓ |
| ⑤ | ALT_TEXT 에 쓰는 캡션에서 " — " 제거(그림처럼) | `store_final.py` | `test_b_ALT_TEXT_가_표_순서_그대로_8줄_LF_이고_140자_이하` | 1 failed ✓ |
| ⑥ | `pick_hero_vehicle()` 이 지정 대상이 있어도 탐색부터 함 | `capture_store_shots.py` | `test_e_지정_대상이_있으면_탐색하지_않는다` | 1 failed ✓ |

전부 의도한 테스트만 빨간불, 나머지는 deselect. 스크립트: 스크래치패드 `mutate.py`(리포 밖).

---

## 7. 확인된 사실 / 추정

**확인된 사실**
- dry-run rc 0, final/ 8장 규격·모드·md5, ALT_TEXT 8줄 최대 27자, 기준월 자동 `2026년 9월 기준` — 실행 로그·파일로 확인.
- final/ == overlay-draft/ md5 8/8 — `md5sum` 대조.
- `capture_store_shots.py --audit` 는 외부 요청 없이 rc 0(원본 8장 md5 == HEAD.json 기록, 사전 대조).
- 변이 6종 결과 — 스크립트 출력 그대로.
- 테스트 전 1267.

**추정**
- 배포 뒤 실촬영(`python tools/store_final.py`, dry-run 아님)의 외부 이동 수: 8회(장당 1회, 대상이 `SUBMIT_TARGETS` 로 고정돼 탐색 0회) × 7초 지연 ≈ 1분 + 페이지 로드. **실측 아님** — 촬영을 이번에 하지 않았다.
- 실촬영에서 `shoot_calendar()` 의 '오늘' 검사와 `shoot_hexa()` 의 6/6축 검사가 통과할지는 그날 데이터에 달렸다(SM6 기일 10-08, G90 기일 10-07 — 지나면 `SUBMIT_TARGETS` 를 비우거나 바꿔야 한다).

---

## 8. 남은 것 · 권고 (결정 필요 없음, 기록)

1. `tools/store_overlay.py --basis` 기본값이 여전히 `"2026년 9월 기준"` 하드코딩이다. `store_final.py` 를 거치면 항상 덮어쓰지만, 오버레이를 **단독**으로 돌리면 낡은 값이 그려진다. 범위 밖이라 손대지 않았다 — 기본값을 없애고 필수 인자로 바꾸는 것을 권고(별 티켓).
2. `(b) --audit` 는 촬영 도구의 `screenshots/store` 만 본다 — `store_final.py --src` 를 다른 곳으로 돌려도 대조 대상은 안 바뀐다(`--src` help 에 적어 둠). 테스트가 `run_audit` 를 막는 이유.
3. `final/` 파일명은 오버레이의 `NN_name__B1.png` 그대로다(어느 안인지 이름이 말한다). 콘솔 업로드는 파일명을 쓰지 않는다.
4. 배포 뒤 실행 경로: `PYTHONIOENCODING=utf-8 python tools/store_final.py` (PowerShell 권장 — Git Bash 는 `MSYS_NO_PATHCONV=1`). 끝나면 `final/HEAD.json` 의 장별 `source_commit` 과 md5 를 이 문서 §3 표와 대조해 **바뀐 장만** 오너에게.
5. 다른 담당의 동시 변경(§머리말)은 이 보고와 무관하다. 커밋할 때 파일을 섞지 않도록 주의.
