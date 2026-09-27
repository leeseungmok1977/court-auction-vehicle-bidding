---
order: 2026-09-27-82
from: qa-engineer
ticket: DOC-1
result: done
verified: 재현
handoff: []
workflow: doc1
---

# DOC-1 · 설계서 '현재와 달라진 점' 초안 사실 대조 (qa, 조각 design)

[요약] 판정은 **fixed** 다. backend 초안(`reports/2026-09-27-doc1-backend-design.md`, 지시서 2026-09-27-78)은 뼈대와 수치가 대부분 맞다.
커밋 5개는 모두 있고 수치 30여 개도 근거에서 다시 찾았다.
그러나 사실 오류 9건과 빠진 큰 차이 7건이 있었다. 고친 본은 §4 에 있다.
가장 무거운 것은 셋이다. ⑴ 감정평가서 행의 근거 두 개가 결론과 반대를 가리킨다. ⑵ A.6 자동 판정 행이 `judgment` 열의 쓰임을 지운다. ⑶ 엔카 터널의 열린 준법 쟁점(COMP-1)이 빠졌다.

- 기준: HEAD `895f26e` + 작업 트리. README·`docs/backlog.md` 에 미커밋 수정이 있다. 설계서 파일은 수정이 없다.
- 저장소 파일은 고치지 않았다. 외부 요청·ssh·커밋은 하지 않았다.

## 1. 오류 — 확인된 사실(코드·git 으로 재현)

| # | 초안 주장 | 문제 | 고침 |
|---|---|---|---|
| E1 | FLOW-02 행: 딥링크 안내의 근거가 `src/collect/courtdoc.py` · 백로그 PS-10 | 두 근거가 **반대**를 가리킨다. `courtdoc.py` 는 KAPA 뷰어 URL 을 만드는 모듈이다. 웹 앱은 이 모듈을 import 하지 않는다(쓰는 곳은 `run_courtdoc_discover.py` 뿐). PS-10 은 f1f202d 이전의 'KAPA 원본 임베드+새탭' 뷰어를 '✅ 완료'로 적은 **낡은 행**이다. '딥링크'라는 말도 부정확하다 — `web/app.py` `vehicle_appraisal` 주석은 "딥링크가 물건 단위로는 안 되어 검색 진입점으로 안내"라고 적는다 | 근거를 `web/app.py` `vehicle_appraisal` · 커밋 f1f202d 로 바꾼다. "'자동차·중기검색' 진입점으로 안내(물건 단위 링크는 안 된다)" |
| E2 | A.6 자동 판정 행: "화면은 이 값이 아니라 `bid_state` 8상태를 그린다" | 과장이다. `judgment` 열은 목록 필터(`vehicles.html` 의 `judgment` select · `/vehicles?judgment=입찰 검토 가능` 링크, `app.py` SQL 필터)와 상세의 '입찰 보류'·'수동 검토' 안내 블록(`detail.html`)에 아직 쓰인다. 또 `bid_state` 의 '추가 유찰 대기'는 설계서 기준(상한가 < 최저가)이 아니라 **최저가 > 예상낙찰가**일 때다 | 판정 칩만 `bid_state` 라고 쓰고, 기준 변경과 `judgment` 의 남은 쓰임을 적는다 |
| E3 | A.4-5 행: "못 찾으면 상태 '미매핑'" | 운영 경로에서는 틀렸다. `service._analyze_item` 은 매핑이 없으면 시세 없이 `status: 완료`, 판정 '시세 신뢰도 낮음, 수동 검토'로 저장한다. `'미매핑'` 을 **쓰는** 곳은 옛 배치 `src/pipeline.py` 뿐이다(`web/`·`service` 는 읽기만 한다) | "시세 없이 저장, 판정 '수동 검토'. '미매핑' 상태는 옛 배치만 쓴다" |
| E4 | 공개/관리자 분리 — `service.public_view`·`PRIVATE_FIELDS` · 커밋 3343a20·05662c3 | `public_view`·`PRIVATE_FIELDS` 를 만든 커밋은 **0fe3b56**(TASK-M01/M02, `git log -S`)이다. 3343a20 은 템플릿 숨김·관리자 전용화, 05662c3 은 관리자 SSH 터널 전용화다 | 0fe3b56 을 더하고 커밋마다 한 일을 괄호로 적는다 |
| E5 | FLOW-90 행: "요청 전 고정 대기(법원 5초)" | 예외가 있다. `courtauction_list.warmup` 은 첫 GET 앞 대기가 없고 두 GET 사이가 `time.sleep(2)` 다. `collect_upcoming`·`daily_update` 가 `new_session(); warmup(cs)` 를 바로 부른다. backend 보고서 §3.4 는 이를 알았지만 본문에 안 넣었다. 그래서 '그대로 유효한 것'의 '지연 필수'가 예외 없이 읽힌다 | FLOW-90 행에 예외를 적고, 유효 목록에서 그 행을 가리킨다 |
| E6 | 그대로 유효: "동급 매칭 연식 ±1년 · 주행거리 ±30%" | 첫 단계일 뿐이다. `market_match.summarize` 의 `tiers` 는 표본이 5건에 못 미치면 ±2년·±50%, ±3년·±80% 로 넓힌다 | 확장 단계를 함께 적는다 |
| E7 | C.5 행: "pytest 만 남았다" | 로컬 통합(소량 실수집)은 수동 실행으로 남아 있다 — README '수집·산정 실행 (검증용, 소량·저속)' 의 `python -m src.pipeline` 등. 2,410 수치는 맞다 | "단위는 pytest(2,410), 로컬 통합은 수동 소량 실행" + TEST-1 |
| E8 | A.2 행: "공개 웹앱(PWA)과 안드로이드 TWA 앱이다" | TWA 는 아직 공개 출시 전이다. 백로그 PLAY-1 은 '심사 대기'(프로덕션 액세스 신청 09-26)다 | "TWA 앱은 비공개 테스트 뒤 프로덕션 심사 대기(PLAY-1)" |
| E9 | 미결정 사항 행: "AI Builder 는 안 쓴다 — 사진은 로컬 CLIP 모델" | 설계서의 미결정 항목은 "AI Builder 사용 여부 (감정평가서 자동 판정)"이다. 사진 답은 질문과 어긋난다 | "감정평가서 판정은 규칙 기반(A.4-4 행)" |

작은 정밀도 수정(오류로 세지 않음):
- A.4-4 행: 보험사고이력 건수는 감정요항·매각물건명세 **둘 다**에서 읽는다. 손상 키워드만 감정요항 본문에 한정한다(`grade_accident` docstring).
- A.6 사고 감가 행: 건수는 **내차피해만** 센다. 상대차피해는 감가에 쓰지 않는다(`service.accident_hit_count`).
- C.4-1 행: 사진 정렬 150건은 로컬 모델이라 외부 요청이 아니다. 분석 80건은 DB 설정 `daily_analyze_limit` 이 양수면 그 값으로 바뀐다(`cap = analyze_limit if … else DAILY_ANALYZE_CAP` — 80 을 넘을 수도 있다).
- FLOW-01 행: 매일 시각은 DB 설정 `daily_time` 이 정한다(코드 기본 "06:00", `_scheduler_loop`). 06:30 은 문서값이다.
- claims 근거 "호출부 `_analyze_item`·재산정 2곳·`src/pipeline.py`": 실제 `calculate` 호출은 `web/service.py` 6곳 + `src/pipeline.py` 1곳이다. 모두 `platform="encar"` 또는 `market_platform` 을 넘긴다. **결론(0.95 가 곱해지는 경로 없음)은 유지된다.**

## 2. 빠진 것 — 넣어야 할 큰 차이

1. **엔카 집 회선 터널의 준법 쟁점(COMP-1)**. `docs/compliance-review.md` §12 가 '차단 뒤 우회 금지' 기준(§6.1-R7·§6.5)과 충돌한다고 적었다(심각도 높음). 백로그 COMP-1 은 "오너 직접 추진 중 — 법률 의견·엔카 제휴"다. A.4-6(약관·robots 준수) 대비 가장 큰 현재 차이인데 초안에 없다.
2. **동급 매칭 확장 단계**(E6).
3. **`bid_state` 의 '유찰 대기' 기준 변경과 '이번 회차 입찰 부적합'(blocked)**(E2).
4. **매일 최종 검토 단계** — `service.review_daily_anomalies` 가 불가능한 낙찰을 법원 상세로 재확인한다(외부 요청 상한 `max_recheck=20`). 설계서에 없는 구성요소이고, C.4-1 하드캡 목록에서도 빠졌다.
5. **테스트 전역 네트워크 가드 없음** — 백로그 TEST-1(todo · P1). C.5 행에 들어가야 한다.
6. **보배드림은 ② HTML 파싱**(`bobae.py` `parse_options`·`parse_price` 정규식). A.4-1 행이 법원·엔카·케이카만 말한다.
7. **법원 `warmup` 2초 예외**(E5).

## 3. 맞는 것 — 재현한 근거

- 커밋 존재(`git cat-file -e`)와 내용(`git show --stat`): d4cc3dd(08-23 초기, 설계서 포함) · f1f202d(09-10, KAPA iframe → 안내) · fdababc(09-27 KCAR-1, config·service·kcar) · 3343a20(09-06 관리자 전용화) · 05662c3(09-06 SSH 터널 관리자). 추가 확인 c8ba980(09-27 백로그 KCAR-1 배포 단위) · 0fe3b56.
- 설계서: `git log` 1건(d4cc3dd), 269줄, 작업 트리 수정 없음.
- config: `platform_weight.kcar 0.95` · `accident_depreciation_rate.minor 0.05` · `accident_depreciation_by_hits` 10/15/22/30 · `risk_premium_rate 0.07` · `acquisition_tax_rate 0.07` · `margin_rate 0.15` · `fixed_costs` 30만+20만 · `condition_costs` 30만/70만/25만/150만/30만 · `year_tol 1` · `mileage_tol 0.30` · `min_sample_count 5` · `kcar_cross_enabled false` · `kcar_blend_max_age_days 7` · `kcar_blend_min_sample 5` · `newcar_daily_cap 2400` · `photo_autosort_daily_cap 150` · `single_source_cap 88` · `model_mapping` 7개 · `requery_daily_cap` 키 없음(기본 20).
- 코드 상수: `ACQ_TAX_COMMERCIAL = 0.05` · `CONF_CUTOFFS` 70/45 · `DAILY_ANALYZE_CAP = 80` · `collect_upcoming(max_pages=25)` · `update_results(max_requests=300)` · `_is_block` (403, 407, 429) · `REQUEST_DELAY_SEC` 법원·엔카·보배 5 / 케이카 6 · `effective_median` `min(0.35, kn/(kn+6))` · `BID_STATES` 8개 · `grade_accident` 반환 none/accident/flood · `repair_cost DEFAULT 500000`.
- 재시도: `src/collect/*.py`·`web/service.py`·`src/pipeline.py` 에 retry·`sleep(30`·backoff 0건.
- 알림: `sw.js` push 0건, `web`·`src`·`tools` 에 smtp·sendmail·teams·webhook·pywebpush 0건. `privacy.html` 도 "별도 푸시 알림은 보내지 않습니다".
- 로그인: `web/auth.py` "인증 미구현 — 익명 tier=1".
- `powerautomate/`·`docs/배포가이드.md`: `git log --all` 0건, 디렉터리 없음.
- 에이전트 정의 16개(`.claude/agents/` 에서 `_` 파일 제외).
- 백로그 상태: KCAR-1 '완료 — 배포 2026-09-27 11:26' · PLAY-1 '심사 대기' · MON-01·02 '보류(blocked)' 절 · AUD-02 'todo · 확인(qa)', 제목 '22대' · AUD-08 '백업 완료' · COMP-1 '오너 직접 추진 중'.
- 테스트 수: `NC_NO_SCHEDULER=1 python -m pytest --collect-only -q` → **2410 tests collected**(23.5초, HEAD 895f26e + 작업 트리).
- 개인정보·비밀값: 초안에 이름·이메일·전화·열쇠·토큰·스냅샷 파일명이 없다. `ENCAR_PROXY` 는 변수 이름뿐이다. 줄 번호 포인터가 없다('269줄'은 분량이다).

## 하지 않은 것 · 미검증

- **pytest 전체 실행은 하지 않았다.** 코드 변경이 없는 문서 작업이다. 그리고 TEST-1(전역 네트워크 가드 없음, todo)이 열려 있어 실행이 외부 요청을 낼 위험이 있다. 지시의 '외부 요청 금지'와 부딪힌다. 수집 수만 재현했다. 통과 여부는 **미검증**이다.
- **라이브 미확인**: 도메인·06:30 실행·터널 생존·서버의 `daily_time`·`daily_analyze_limit` 값. 참고로 09-27 감사 S4(`reports/2026-09-27-audit-s4-ops.md` F13)가 openssl 로 `naechaget.co.kr` 인증서를 확인했다(SAN 에 co.kr 포함).
- 화면 캡처는 해당 없다(화면 변경 없음).

## Steward 판단 거리(초안 밖)

- **백로그 PS-10 행이 낡았다.** '감정평가서 원본 인앱 뷰어 — 임베드+새탭 ✅ 완료'라고 적혀 있다. 하지만 f1f202d 가 안내 페이지로 바꿨다. backend 보고서 §3.2 도 PS-10 을 딥링크 근거로 읽었다. 같은 오독이 또 나오지 않게 상태 칸을 고칠 것을 권한다.
- `src/collect/courtdoc.py` 는 웹 앱에서 쓰이지 않는다. 모듈 docstring 은 아직 'KAPA 원본을 그대로 연결'이라 말한다.
- README 작업 트리(미커밋)가 이미 설계서의 '현재와 달라진 점' 절을 가리킨다. 이 절을 넣는 커밋과 같은 커밋으로 묶어야 링크가 빈 곳을 가리키지 않는다.

## 4. 고친 본문

## 0. 현재와 달라진 점 (2026-09-27 기준)

> 이 절은 v1.0 원문을 2026-09-27 의 코드·설정·운영 문서와 절마다 대조해 **달라진 것만** 적었다.
> 아래 본문(Part A~D·미결정 사항)은 2026-08-17 작성 원문 그대로다. 이 절과 어긋나면 원문이 낡은 것이다.
> 지금 진행 현황은 [docs/backlog.md](docs/backlog.md), 날짜별 변경은 [docs/changelog.md](docs/changelog.md) 에 있다. 이 절도 09-27 시점이다.

| 설계서(절) | 설계서가 말하는 것 | 지금 | 근거 |
|---|---|---|---|
| A.1 수집 실행 | Power Automate 클라우드 흐름(HTTP 액션) | 파이썬 파이프라인이 운영 도구다(사용자 승인 아키텍처 변경). 웹 앱 내장 스케줄러가 매일 갱신한다. 관리자가 수동으로도 돌린다 | CLAUDE.md '아키텍처 변경' · `web/service.py` `daily_update`·`start_scheduler` · `web/daily.py` |
| A.1 제외 '상시 서버 운영' | 상시 서버를 두지 않는다 | AWS EC2(서울) 상시 배포다. systemd `naechaget` + nginx + HTTPS. 공개 주소는 naechaget.co.kr (문서 기준, 라이브 미확인) | `docs/DEPLOY_AWS.md` · `deploy/vm_setup.sh` · README '운영 배포' |
| A.1·A.2 저장소 | SharePoint 문서 라이브러리 + 목록 7종 | SQLite `data/auction.db` + 물건 폴더 `data/{사건번호}_{물건번호}/`(detail.json·appraisal.txt·photos/). 루트는 환경변수 `DATA_DIR` 로 바꾼다 | `web/db.py` `DB_PATH`·`_SCHEMA` · `src/paths.py` · `courtauction_detail.save_item_folder` |
| A.5 목록 7종 | 물건·기일이력·시중매물·시세요약·입찰검토·수집로그·설정 | 물건·시세요약·입찰검토는 `vehicles` 한 테이블의 열이다. 기일이력=`dxdy_history`(JSON). 시중매물=`comps`(JSON, 중앙값에 쓴 매물만). 수집로그=`runs`·`anomaly_log`. 설정=`config.yaml`+`settings`. 낙찰은 `sale_results` 에 누적한다 | `web/db.py` `_SCHEMA` |
| A.2 사용자 접점 | Teams/메일 알림 · SharePoint 리포트 | 공개 웹앱(PWA)이다. 안드로이드 TWA 앱은 비공개 테스트를 마치고 프로덕션 심사 대기다(PLAY-1). 로그인은 없다(익명). 메일·푸시·Teams 발송 코드는 없다. 임박 기일은 대시보드 '임박 매각기일'(3일 이내) 패널과 헤더 배지로 보인다. 리포트는 물건별 웹 리포트(인쇄→PDF)다 | `web/templates/dashboard.html` '임박 매각기일' · `web/templates/privacy.html` '별도 푸시 알림은 보내지 않습니다' · `web/static/manifest.webmanifest` · `android/twa-manifest.json` · `web/auth.py` · 백로그 PLAY-1 |
| A.2·A.5 최종입찰가 확정 | 입찰검토 목록에 기록 | 즐겨찾기·메모·최종입찰가는 서버가 아니라 사용자 기기(localStorage)에 둔다. DB 열은 레거시로 남았다 | `docs/MONETIZATION_SPEC.md` §2 · `web/templates/base.html` '기기 로컬 저장' |
| A.3 FLOW-01 목록 | 예약 1일 1~2회 | `src/collect/courtauction_list.py` + `service.collect_upcoming`. 매각기일 30일 이내 전국 자동차 전체를 런당 25페이지(쪽당 40건)까지 본다. 하루 1회다. 시각은 DB 설정 `daily_time` 이 정한다(코드 기본 06:00, 문서상 운영 06:30) | README '매일 자동 갱신' · `service._scheduler_loop` · 백로그 KCAR-1 |
| A.3 FLOW-02 상세·첨부 | 감정평가서 PDF·사진 다운로드 | 상세·사진(base64)·감정요항 텍스트는 `courtauction_detail.py` 가 받는다. 감정평가서 PDF는 저장하지 않는다. 상세의 [감정평가서] 버튼은 안내 페이지를 연다. 원본은 법원경매정보 '자동차·중기검색' 진입점으로 안내한다(물건 단위 링크는 안 된다). KAPA 는 서버에서 차단된다 | `web/app.py` `vehicle_appraisal` · 커밋 f1f202d |
| A.3 FLOW-03 엔카 | 예약 + 신규 물건 시 | `src/collect/encar.py`. 매일 갱신 안에서 런당 80건. 서버 IP 가 407 로 차단돼(09-07경) 엔카 요청만 집 회선 역방향 터널로 나간다. 이 우회의 준법 쟁점은 A.4-6 행 | `docs/HOME_TUNNEL.md` · `service.daily_update` · `encar.new_session`(`ENCAR_PROXY`) |
| A.3 FLOW-04 케이카 | 케이카 동급 수집 | **중지**(2026-09-27 KCAR-1, 오너 승인, 백로그상 같은 날 배포). 수집하지 않는다. 저장된 값도 가격·신뢰도에 섞지 않는다. 재개는 오너 승인과 준법 §12 재검토가 먼저다 | config `kcar_cross_enabled: false` · `service.kcar_value_usable` · 커밋 fdababc · 백로그 KCAR-1 · `docs/compliance-review.md` §12 |
| A.3 FLOW-05 산정 | 시세 통계 → 산정 → 입찰검토 기록 | 통계·신뢰도는 `src/parse/market_match.py`, 산식은 `src/bidcalc/calculator.py` `calculate`, 판정·예상낙찰가는 `web/service.py`. 결과는 `vehicles` 열에 쓴다 | 각 함수 |
| A.3 FLOW-06 알림·리포트 | D-7/3/1 Teams/메일 발송 | 사용자에게 보내는 것은 없다(위 A.2 행). 운영 보고는 사내용이다 — 매일 12시·주간·월간 | `tools/daily_ops_report.py`·`weekly_report.py`·`monthly_report.py` · `docs/ORG.md` §4 |
| A.3 FLOW-90 공통 HTTP | 3~10초 랜덤 지연·재시도·수집로그 | 공통 모듈이 없다. 수집 모듈마다 요청 전 고정 대기(법원·엔카·보배 5초, 케이카 최소 간격 6초)와 차단 판정을 둔다. 예외가 하나 있다 — 법원 세션 `warmup` 은 첫 GET 앞에 대기가 없고 두 GET 사이가 2초다. 재시도 루프는 없다. 실행 기록은 `runs` 다 | `src/collect/*.py` `REQUEST_DELAY_SEC` · `courtauction_list.warmup`·`_check_block` · `service._is_block` |
| A.4-1 파싱 우선순위 | ① 내부 JSON ② HTML ③ Office Script ④ PA Desktop | 법원·엔카는 ① 내부 JSON 으로 끝났다. 보배드림(출시가)은 ② HTML 파싱이다. 케이카만 요청이 암호화라 브라우저(Playwright) 응답 가로채기를 썼다(지금 중지). ③·④는 안 쓴다 | README '확인된 엔드포인트' · `src/collect/bobae.py` · `src/collect/kcar.py` |
| A.4-4 사고유무 | 키워드 1차 + 카히스토리 수동 병기, AI Builder 추후 | 규칙 기반 자동 판정이다. 보험사고이력 건수는 감정요항과 매각물건명세 둘 다에서 읽는다. 손상 키워드는 감정요항 본문에서만 찾는다. 등급은 none·accident·flood 셋이다(단순수리 `minor` 는 파서가 만들지 않는다). 카히스토리 직접 조회·AI Builder 는 없다 | `src/parse/detail_parser.py` `grade_accident` · config `accident_keywords`·`flood_keywords` |
| A.4-5 모델매핑 | 설정 목록 매핑 테이블, 미매핑 시 알림 | ① config `model_mapping`(7개 차종) ② 사용자 검색 차명 ③ `encar.auto_map` 자동 추정(화물·제네시스·국산·수입 분기) 순이다. 못 찾으면 시세 없이 저장하고 판정은 '시세 신뢰도 낮음, 수동 검토'다. 알림은 없다. '미매핑' 상태는 옛 배치(`src/pipeline.py`)만 쓴다 | `service._resolve_encar`·`_analyze_item` · `src/collect/encar.py` `auto_map` |
| A.4-6 준법 | 약관·robots.txt 준수 | 엔카 API 의 robots.txt 는 전면 Disallow 다. 사용자 명시 지시(2026-08-17)로 소량·저속 수집한다. 407 차단 뒤 집 회선 터널로 우회하는 것은 '차단 뒤 우회 금지' 기준과 충돌한다는 준법 지적이 열려 있다(COMP-1, 오너 직접 추진 중 — 법률 의견·엔카 제휴). 케이카는 약관 미확인 상태의 자동 재개 위험(§12)과 낡은 값 문제로 멈췄다. 시세 출처명·매물 링크는 공개하지 않는다 | README '엔카 준법 주의' · `docs/compliance-review.md` §1·§12 · 백로그 COMP-1 · `service._scrub_source` |
| A.6 기준시세 | 중앙값 × 플랫폼 가중(엔카 1.0 / 케이카 0.95) | 엔카 동급 중앙값 그대로다(가중 1.0). config `platform_weight.kcar: 0.95` 는 남아 있지만 호출부가 넘기지 않아 쓰이지 않는다. 케이카는 0.95 가중이 아니라 `effective_median` 표본 가중(상한 35%)으로 섞였다. KCAR-1 뒤로는 섞지 않는다. 엔카가 없으면 DB 동급 시세를 '동급 참조'로 빌린다 | `calculator.calculate` · `service.effective_median`·`_blend_ok`·`reuse_market_prices` |
| A.6 사고 감가 | 단순수리 5% / 사고 10~20% | 내차피해 건수별 10%(1회)·15%(2~3회)·22%(4~6회)·30%(7회+)다. 상대차피해는 세지 않는다. 실측이 아닌 가정이다. 이력을 확인 못 한 차는 사고로 가정해 15% | config `accident_depreciation_by_hits`·`accident_depreciation_rate` · `service.use_accident_rate`·`accident_hit_count` |
| A.6 리스크·부대비·마진 | 리스크 5~10% · 취득세 7% + 이전·탁송 · 마진 10~15% | 리스크 7% · 취득세 7%(화물·특수 5%) · 이전 30만 + 탁송 20만 · 마진 15%. 예상 수리비 기본값 50만. 감정요항 상태 비용(외관 30만/70만·검사경과 25만·운행불가 150만)과 사진 없음 30만도 뺀다 | config `risk_premium_rate`·`acquisition_tax_rate`·`fixed_costs`·`margin_rate`·`condition_costs` · `service.tax_rate_for` · `web/db.py` `repair_cost` |
| A.6 자동 판정 | 유찰 대기 · 신뢰도 낮음 · 입찰 보류 | 이 세 판정은 `calculate` 에 그대로 있고 `judgment` 열에 저장된다. 신뢰도가 '낮음'이면 '수동 검토'로 내린다. 판정 칩은 `bid_state` 한 곳의 8상태를 그린다. 그 '추가 유찰 대기'는 상한가가 아니라 최저가가 예상낙찰가보다 높을 때다. 최저가가 실사용 상한선을 넘으면 '이번 회차 입찰 부적합'이다. `judgment` 열은 목록 필터(`?judgment=`)와 상세의 보류·수동 검토 안내에 아직 쓰인다 | `calculator.Judgment` · `service._final_judgment`·`bid_state` · `web/templates/vehicles.html`·`detail.html` |
| A.6 파라미터 위치 | '설정' 목록 | `config.yaml` 이 단일 진실원천이다. 단 일부 상수는 아직 코드에 있다(화물 취득세 5%·신뢰도 구간 70/45·분석 런당 80건) | `service.ACQ_TAX_COMMERCIAL`·`CONF_CUTOFFS`·`daily_update` |
| A.7 라이선스·제약 | HTTP 프리미엄 라이선스가 선결 | 해당 없다(PA 미사용). 호출 한도는 라이선스가 아니라 우리가 거는 런당 하드캡이다(C.4-1 행) | README '선결조건' |
| Part B 사전분석 | 사람이 F12 로 요청을 복사해 `capture/` 에 저장 | 사람 캡처 대신 사이트 화면정의(WebSquare XML)와 실제 응답을 분석해 엔드포인트를 실측했다 | README '진행 현황' 참고 절 |
| C.1 저장소 구조 | `auction-vehicle/` · `powerautomate/` | `powerautomate/` 는 만든 적이 없다(git 이력 0건). 대신 `web/`·`deploy/`·`android/`·`tools/`·`scripts/`·`src/vision/`·`orders/`·`reports/` 가 있다 | `git log --all -- powerautomate` |
| C.2 사람 입력 | `sharepoint.txt` · `sample_export.zip` · 라이선스 확인 | 필요 없다(PA 대체) | README '선결조건' |
| C.3 태스크 | TASK-00~08 | TASK-00~05 완료(05 는 엔카 기준) · TASK-06·07 은 PA 대체로 보류 · TASK-08 진행. 그 뒤 일은 백로그 티켓으로 관리한다 | README '진행 현황' 표 · `docs/backlog.md` |
| C.4-1 소량 원칙 | 검증 3페이지·2건. 전체 수집을 파이썬으로 하지 않는다 | 검증은 그대로 3페이지·2건이다. 운영 수집은 파이썬이 하되 런당 하드캡을 건다 — 목록 25페이지 · 분석 80건 · 0표본 재조회 20그룹 · 최종 검토 재확인 20건 · 낙찰결과 300요청 · 출시가 하루 2,400요청. 분석 상한은 DB 설정 `daily_analyze_limit` 이 양수면 그 값으로 바뀐다. 사진 정렬 150건은 로컬 모델이라 외부 요청이 없다 | CLAUDE.md C.4-1 · `service.collect_upcoming`·`daily_update`·`requery_missing_market`·`review_daily_anomalies`·`update_results` · config `newcar_daily_cap`·`photo_autosort_daily_cap` |
| C.4-5 중단 조건 | 403/429·CAPTCHA·비정상 3회 연속 | 407 을 더했다(엔카가 서버 IP 를 막을 때 낸 코드). 엔카 차단이면 그 단계만 멈추고 낙찰결과 등 뒤 단계는 계속한다 | `service._is_block` · `service.daily_update` |
| C.5 테스트 | 단위·로컬 통합·definition 검증·흐름 체크리스트 | 단위는 pytest 다(09-27 수집 2,410건). 로컬 통합은 수동 소량 실행으로 남았다(`python -m src.pipeline` 등). definition 검증·흐름 체크리스트는 없다. 테스트에 전역 네트워크 가드가 아직 없다(TEST-1, todo) | `python -m pytest --collect-only -q` · README '수집·산정 실행' · 백로그 TEST-1 |
| Part D 최종 검수 | SharePoint 폴더·입찰검토·수집로그 확인 | 해당 없다. 완료는 백로그 티켓의 DoD 원문 대조로 판정한다 | CLAUDE.md 운영 규칙 7 |
| 미결정 사항 | 라이선스·목적·차종·수집 범위·AI Builder | 라이선스는 불필요. 목적은 재판매(마진 15%)로 정했고 실사용 상한선도 함께 낸다. 차종·가격대 제한은 없다(30일 이내 전 물건). 수집 범위는 A.4-1 행. AI Builder 는 안 쓴다 — 감정평가서 판정은 규칙 기반이다(A.4-4 행) | README '선결조건' · `service.personal_use_max_bid` |

**설계서에 없는데 지금 있는 큰 구성요소**
- 판정 한 곳(`bid_state` 8상태)과 시세 신뢰도 점수(0~100, 단일 소스 상한 88) — `web/service.py` `bid_state` · `src/parse/market_match.py` · config `appraisal_guard`
- 예상낙찰가(최저매각가 × 유찰 프리미엄)와 낙찰 누적·백테스트 — `service.expected_for`·`backtest_stats` · `web/db.py` `sale_results`
- 실사용 상한선(이 값을 넘겨 낙찰받으면 소매가 낫다) — `service.personal_use_max_bid`
- 감정요항 파싱(검사 유효·외관 상태·운행 가능) — `src/parse/appraisal.py`
- 사진 분류: 매일 로컬 CLIP 정렬 + 주간 비전 검수 — `src/parse/photo_autosort.py` · `.claude/agents/photo-classifier.md`
- 당시 출시가(신차가) — `src/collect/bobae.py` · `docs/compliance-review.md` §6 · config `newcar_public`
- 운영 감시(수집·분석 멈춤 경보) — `web/ops_health.py` · config `ops_alert`
- 매일 최종 검토(불가능한 낙찰을 법원 상세로 재확인하고, 그래도 이상하면 등록 보류) — `service.review_daily_anomalies` · `web/db.py` `anomaly_log`
- 공개/관리자 분리(출처·원자료 비공개) — `service.public_view`·`PRIVATE_FIELDS` · 커밋 0fe3b56(데이터 계층 격리)·3343a20(관리자 전용화)·05662c3(관리자는 SSH 터널로만)
- 수익화 준비(결제·회원은 보류, MON-01·02)와 Play 출시(PLAY-1 심사 대기) — `docs/MONETIZATION_SPEC.md` · `docs/backlog.md`
- 에이전트 조직(16자리)과 순환계(지시서·보고서 머리말·당직) — `docs/ORG.md` · `docs/org-contracts.md` · `tools/org_runtime.py`
- 엔카 집 회선 터널(준법 쟁점 COMP-1) · DB 백업(AUD-08) — `docs/HOME_TUNNEL.md` · `deploy/backup_db.sh`

**그대로 유효한 것**
- C.4 뼈대: 지연 필수(예외는 FLOW-90 행의 `warmup`) · 추측 금지 · 비밀정보 git 제외 · 차단 즉시 중단 · 첫 외부 요청 전 승인 — CLAUDE.md C.4 · `.gitignore`(`capture/`·`data/`·`*.har`)
- 세션 2단계 패턴(첫 진입에서 쿠키를 받아 재사용, 하드코딩 없음) — `courtauction_list.new_session`·`warmup`
- 공식 API 가 없다는 전제와 내부 JSON 요청 우선 — README '확인된 엔드포인트'
- 동급 매칭은 연식 ±1년 · 주행거리 ±30% 에서 시작한다. 표본이 5건에 못 미치면 ±2년·±50%, ±3년·±80% 로 넓힌다 — config `year_tol`·`mileage_tol` · `market_match.summarize`(`tiers`)·`filter_comparable`
- 산식 뼈대(기준시세 − 수리비 − 사고감가 − 리스크 − 취득부대 − 마진), 권장 범위 [최저매각가, 상한가], 표본 5건 미만 → 신뢰도 낮음, 침수·전손 → 보류 — `calculator.calculate` · config `min_sample_count`·`flood_keywords`
- 변경 감지 키 사건번호+물건번호(`vehicles.id`). ⚠ 다른 법원의 같은 사건번호가 부딪혀 매일 22대를 버린다 — AUD-02(todo)
