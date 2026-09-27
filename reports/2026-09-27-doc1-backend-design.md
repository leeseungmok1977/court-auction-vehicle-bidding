---
order: 2026-09-27-78
from: backend-engineer
ticket: DOC-1
result: done
verified: 재현
handoff: []
workflow: doc1
---

# DOC-1 · 통합 설계서 v1.0 대조 — '현재와 달라진 점' 초안 (backend)

[요약] v1.0 원문(269줄, 08-23 첫 커밋 `d4cc3dd` 뒤 변경 0)을 절마다 코드·config·git·문서와 대조했다.
달라진 것 32행, 새 구성요소 11줄, 그대로 유효한 것 6줄로 초안을 만들었다(61줄, 90줄 이내).
저장소 파일은 고치지 않았다. 코드·API 응답 스키마·DB 스키마 변경은 없다.

- 기준 커밋: HEAD `895f26e` (작업 트리에 README·backlog 미커밋 수정이 있는 상태에서 읽음)
- 대상 파일은 `법원경매_차량_입찰가산정_통합설계서_v1.0.md` 이다. 이 초안은 그 맨 앞에 붙일 절이다.

## 1. 초안 (그대로 붙일 본문)

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
| A.2 사용자 접점 | Teams/메일 알림 · SharePoint 리포트 | 공개 웹앱(PWA)과 안드로이드 TWA 앱이다. 로그인은 없다(익명). 메일·푸시·Teams 발송 코드는 없다. 임박 기일은 대시보드 '임박 매각기일'(3일 이내) 패널에 보인다. 리포트는 물건별 웹 리포트(인쇄→PDF)다 | `web/templates/dashboard.html` '임박 매각기일' · `web/static/manifest.webmanifest` · `android/twa-manifest.json` · `web/auth.py` · 백로그 PLAY-1 |
| A.2·A.5 최종입찰가 확정 | 입찰검토 목록에 기록 | 즐겨찾기·메모·최종입찰가는 서버가 아니라 사용자 기기(localStorage)에 둔다. DB 열은 레거시로 남았다 | `docs/MONETIZATION_SPEC.md` §2 · `web/templates/base.html` '기기 로컬 저장' |
| A.3 FLOW-01 목록 | 예약 1일 1~2회 | `src/collect/courtauction_list.py` + `service.collect_upcoming`. 매각기일 30일 이내 전국 자동차 전체를 런당 25페이지까지 본다. 매일 06:30 경(문서 기준) | README '매일 자동 갱신' · 백로그 KCAR-1 |
| A.3 FLOW-02 상세·첨부 | 감정평가서 PDF·사진 다운로드 | 상세·사진(base64)·감정요항 텍스트는 `courtauction_detail.py` 가 받는다. 감정평가서 PDF는 저장하지 않는다. 원본은 법원경매정보 딥링크로 안내한다(KAPA 는 서버에서 차단) | `src/collect/courtdoc.py` · 백로그 PS-10 · 커밋 f1f202d |
| A.3 FLOW-03 엔카 | 예약 + 신규 물건 시 | `src/collect/encar.py`. 매일 갱신 안에서 런당 80건. 서버 IP 가 407 로 차단돼(09-07경) 엔카 요청만 집 회선 역방향 터널로 나간다 | `docs/HOME_TUNNEL.md` · `service.daily_update` · `encar.new_session`(`ENCAR_PROXY`) |
| A.3 FLOW-04 케이카 | 케이카 동급 수집 | **중지**(2026-09-27 KCAR-1, 오너 승인). 수집하지 않는다. 저장된 값도 가격·신뢰도에 섞지 않는다. 재개는 오너 승인과 준법 §12 재검토가 먼저다 | config `kcar_cross_enabled: false` · `service.kcar_value_usable` · 커밋 fdababc · `docs/compliance-review.md` §12 |
| A.3 FLOW-05 산정 | 시세 통계 → 산정 → 입찰검토 기록 | 통계·신뢰도는 `src/parse/market_match.py`, 산식은 `src/bidcalc/calculator.py` `calculate`, 판정·예상낙찰가는 `web/service.py`. 결과는 `vehicles` 열에 쓴다 | 각 함수 |
| A.3 FLOW-06 알림·리포트 | D-7/3/1 Teams/메일 발송 | 사용자에게 보내는 것은 없다(위 A.2 행). 운영 보고는 사내용이다 — 매일 12시·주간·월간 | `tools/daily_ops_report.py`·`weekly_report.py`·`monthly_report.py` · `docs/ORG.md` §4 |
| A.3 FLOW-90 공통 HTTP | 3~10초 랜덤 지연·재시도·수집로그 | 공통 모듈이 없다. 수집 모듈마다 요청 전 고정 대기(법원·엔카·보배 5초, 케이카 6초)와 차단 판정을 둔다. 재시도 루프는 없다. 실행 기록은 `runs` 다 | `src/collect/*.py` `REQUEST_DELAY_SEC` · `courtauction_list._check_block` · `service._is_block` |
| A.4-1 파싱 우선순위 | ① 내부 JSON ② HTML ③ Office Script ④ PA Desktop | 법원·엔카는 ① 내부 JSON 으로 끝났다. 케이카만 요청이 암호화라 브라우저(Playwright) 응답 가로채기를 썼다(지금 중지). ③·④는 안 쓴다 | README '확인된 엔드포인트' · `src/collect/kcar.py` |
| A.4-4 사고유무 | 키워드 1차 + 카히스토리 수동 병기, AI Builder 추후 | 규칙 기반 자동 판정이다. 감정요항 손상 키워드와 매각물건명세에 실린 보험사고이력 건수를 읽는다. 등급은 none·accident·flood 셋이다(단순수리 `minor` 는 파서가 만들지 않는다). 카히스토리 직접 조회·AI Builder 는 없다 | `src/parse/detail_parser.py` `grade_accident` · config `accident_keywords`·`flood_keywords` |
| A.4-5 모델매핑 | 설정 목록 매핑 테이블, 미매핑 시 알림 | ① config `model_mapping`(7개 차종) ② 사용자 검색 차명 ③ `encar.auto_map` 자동 추정(국산·수입·화물 분기) 순이다. 못 찾으면 상태 '미매핑'. 알림은 없다 | `service._resolve_encar` · `src/collect/encar.py` `auto_map` |
| A.4-6 준법 | 약관·robots.txt 준수 | 엔카 API 의 robots.txt 는 전면 Disallow 다. 사용자 명시 지시(2026-08-17)로 소량·저속 수집한다. 케이카는 약관 미확인 상태의 자동 재개 위험(§12)과 낡은 값 문제로 멈췄다. 시세 출처명·매물 링크는 공개하지 않는다 | README '엔카 준법 주의' · `docs/compliance-review.md` §1·§12 · `service._scrub_source` |
| A.6 기준시세 | 중앙값 × 플랫폼 가중(엔카 1.0 / 케이카 0.95) | 엔카 동급 중앙값 그대로다(가중 1.0). config `platform_weight.kcar: 0.95` 는 남아 있지만 호출부가 넘기지 않아 쓰이지 않는다. 케이카는 0.95 가중이 아니라 `effective_median` 표본 가중(상한 35%)으로 섞였다. KCAR-1 뒤로는 섞지 않는다. 엔카가 없으면 DB 동급 시세를 '동급 참조'로 빌린다 | `calculator.calculate` · `service.effective_median`·`_blend_ok`·`reuse_market_prices` |
| A.6 사고 감가 | 단순수리 5% / 사고 10~20% | 사고 건수별 10%(1회)·15%(2~3회)·22%(4~6회)·30%(7회+)다. 실측이 아닌 가정이다. 이력을 확인 못 한 차는 사고로 가정해 15% | config `accident_depreciation_by_hits`·`accident_depreciation_rate` · `service.use_accident_rate` |
| A.6 리스크·부대비·마진 | 리스크 5~10% · 취득세 7% + 이전·탁송 · 마진 10~15% | 리스크 7% · 취득세 7%(화물·특수 5%) · 이전 30만 + 탁송 20만 · 마진 15%. 예상 수리비 기본값 50만. 감정요항 상태 비용(외관 30만/70만·검사경과 25만·운행불가 150만)과 사진 없음 30만도 뺀다 | config `risk_premium_rate`·`acquisition_tax_rate`·`fixed_costs`·`margin_rate`·`condition_costs` · `service.tax_rate_for` · `web/db.py` `repair_cost` |
| A.6 자동 판정 | 유찰 대기 · 신뢰도 낮음 · 입찰 보류 | 이 판정은 `calculate` 에 그대로 있다. 신뢰도가 '낮음'이면 '수동 검토'로 내린다. 화면은 이 값이 아니라 `bid_state` 한 곳의 8상태를 그린다 | `calculator.Judgment` · `service._final_judgment`·`bid_state` |
| A.6 파라미터 위치 | '설정' 목록 | `config.yaml` 이 단일 진실원천이다. 단 일부 상수는 아직 코드에 있다(화물 취득세 5%·신뢰도 구간 70/45·분석 런당 80건) | `service.ACQ_TAX_COMMERCIAL`·`CONF_CUTOFFS`·`daily_update` |
| A.7 라이선스·제약 | HTTP 프리미엄 라이선스가 선결 | 해당 없다(PA 미사용). 호출 한도는 라이선스가 아니라 우리가 거는 런당 하드캡이다(C.4-1 행) | README '선결조건' |
| Part B 사전분석 | 사람이 F12 로 요청을 복사해 `capture/` 에 저장 | 사람 캡처 대신 사이트 화면정의(WebSquare XML)와 실제 응답을 분석해 엔드포인트를 실측했다 | README '진행 현황' 참고 절 |
| C.1 저장소 구조 | `auction-vehicle/` · `powerautomate/` | `powerautomate/` 는 만든 적이 없다(git 이력 0건). 대신 `web/`·`deploy/`·`android/`·`tools/`·`scripts/`·`src/vision/`·`orders/`·`reports/` 가 있다 | `git log --all -- powerautomate` |
| C.2 사람 입력 | `sharepoint.txt` · `sample_export.zip` · 라이선스 확인 | 필요 없다(PA 대체) | README '선결조건' |
| C.3 태스크 | TASK-00~08 | TASK-00~05 완료(05 는 엔카 기준) · TASK-06·07 은 PA 대체로 보류 · TASK-08 진행. 그 뒤 일은 백로그 티켓으로 관리한다 | README '진행 현황' 표 · `docs/backlog.md` |
| C.4-1 소량 원칙 | 검증 3페이지·2건. 전체 수집을 파이썬으로 하지 않는다 | 검증은 그대로 3페이지·2건이다. 운영 수집은 파이썬이 하되 런당 하드캡을 건다 — 목록 25페이지 · 분석 80건 · 0표본 재조회 20그룹 · 낙찰결과 300요청 · 출시가 하루 2,400요청 · 사진 정렬 150건 | CLAUDE.md C.4-1 · `service.collect_upcoming`·`daily_update`·`requery_missing_market`·`update_results` · config `newcar_daily_cap`·`photo_autosort_daily_cap` |
| C.4-5 중단 조건 | 403/429·CAPTCHA·비정상 3회 연속 | 407 을 더했다(엔카가 서버 IP 를 막을 때 낸 코드). 엔카 차단이면 그 단계만 멈추고 낙찰결과 등 뒤 단계는 계속한다 | `service._is_block` · `service.daily_update` |
| C.5 테스트 | 단위·로컬 통합·definition 검증·흐름 체크리스트 | pytest 만 남았다. 09-27 수집 2,410건. definition 검증·흐름 체크리스트는 없다 | `python -m pytest --collect-only -q` |
| Part D 최종 검수 | SharePoint 폴더·입찰검토·수집로그 확인 | 해당 없다. 완료는 백로그 티켓의 DoD 원문 대조로 판정한다 | CLAUDE.md 운영 규칙 7 |
| 미결정 사항 | 라이선스·목적·차종·수집 범위·AI Builder | 라이선스는 불필요. 목적은 재판매(마진 15%)로 정했고 실사용 상한선도 함께 낸다. 차종·가격대 제한은 없다(30일 이내 전 물건). 수집 범위는 A.4-1 행. AI Builder 는 안 쓴다 — 사진은 로컬 CLIP 모델 | README '선결조건' · `service.personal_use_max_bid` · `src/parse/photo_autosort.py` |

**설계서에 없는데 지금 있는 큰 구성요소**
- 판정 한 곳(`bid_state` 8상태)과 시세 신뢰도 점수(0~100, 단일 소스 상한 88) — `web/service.py` `bid_state` · `src/parse/market_match.py` · config `appraisal_guard`
- 예상낙찰가(최저매각가 × 유찰 프리미엄)와 낙찰 누적·백테스트 — `service.expected_for`·`backtest_stats` · `web/db.py` `sale_results`
- 실사용 상한선(이 값을 넘겨 낙찰받으면 소매가 낫다) — `service.personal_use_max_bid`
- 감정요항 파싱(검사 유효·외관 상태·운행 가능) — `src/parse/appraisal.py`
- 사진 분류: 매일 로컬 CLIP 정렬 + 주간 비전 검수 — `src/parse/photo_autosort.py` · `.claude/agents/photo-classifier.md`
- 당시 출시가(신차가) — `src/collect/bobae.py` · `docs/compliance-review.md` §6 · config `newcar_public`
- 운영 감시(수집·분석 멈춤 경보) — `web/ops_health.py` · config `ops_alert`
- 공개/관리자 분리(출처·원자료 비공개) — `service.public_view`·`PRIVATE_FIELDS` · 커밋 3343a20·05662c3
- 수익화 준비(결제·회원은 보류, MON-01·02)와 Play 출시(PLAY-1 심사 대기) — `docs/MONETIZATION_SPEC.md` · `docs/backlog.md`
- 에이전트 조직(16자리)과 순환계(지시서·보고서 머리말·당직) — `docs/ORG.md` · `docs/org-contracts.md` · `tools/org_runtime.py`
- 엔카 집 회선 터널 · DB 백업 — `docs/HOME_TUNNEL.md` · `deploy/backup_db.sh`

**그대로 유효한 것**
- C.4 뼈대: 지연 필수 · 추측 금지 · 비밀정보 git 제외 · 차단 즉시 중단 · 첫 외부 요청 전 승인 — CLAUDE.md C.4 · `.gitignore`(`capture/`·`data/`·`*.har`)
- 세션 2단계 패턴(첫 진입에서 쿠키를 받아 재사용, 하드코딩 없음) — `courtauction_list.new_session`·`warmup`
- 공식 API 가 없다는 전제와 내부 JSON 요청 우선 — README '확인된 엔드포인트'
- 동급 매칭 연식 ±1년 · 주행거리 ±30% — config `year_tol`·`mileage_tol` · `market_match.filter_comparable`
- 산식 뼈대(기준시세 − 수리비 − 사고감가 − 리스크 − 취득부대 − 마진), 권장 범위 [최저매각가, 상한가], 표본 5건 미만 → 신뢰도 낮음, 침수·전손 → 보류 — `calculator.calculate` · config `min_sample_count`·`flood_keywords`
- 변경 감지 키 사건번호+물건번호(`vehicles.id`). ⚠ 다른 법원의 같은 사건번호가 부딪혀 매일 22대를 버린다 — AUD-02(todo)

## 2. 무엇을 어떻게 확인했나 (조건 명시)

확인된 사실(코드·config·git 으로 재현):
- 케이카 0.95 가중이 죽은 값인 것: `platform_weight` 사용처는 `calculator.calculate` 한 곳뿐이다(grep).
  `calculate` 를 부르는 곳은 `service._analyze_item`·재산정 2곳·`src/pipeline.py` 다.
  넘기는 `platform` 은 `"encar"` 또는 `market_platform`(값은 `encar`·`동급참조`·NULL 뿐, 대입처 grep)이다.
  `동급참조` 는 `.get(…, 1.0)` 기본값을 탄다. 그래서 0.95 가 곱해지는 경로가 없다.
- 케이카 값이 섞이던 경로: `service.effective_median` 표본 가중 `min(0.35, n/(n+6))`. 게이트는 `kcar_value_usable`(설정·나이 7일·표본 5건).
- `minor` 등급: `detail_parser.grade_accident` 는 `"flood"`·`"accident"`·`"none"` 만 돌려준다. `minor` 는 `calculator._demo` 에만 있다.
- 알림 발송: `web/static/sw.js` 에 `push` 0건. `web/`·`src/`·`tools/` 에 smtp·sendmail·teams·webhook 0건.
- 로그인: `web/auth.py` "인증 미구현 — 익명 tier=1". `web/app.py` 에 로그인 라우트 없음.
- 재시도: `src/collect/*.py`·`web/service.py` 에 retry·`sleep(30` 0건.
- 하드캡: `collect_upcoming(max_pages=25)`, `daily_update` 의 `DAILY_ANALYZE_CAP = 80`, `update_results(max_requests=300)`,
  `requery_daily_cap` 은 config 에 키가 없어 기본 20. `newcar_daily_cap: 2400`·`photo_autosort_daily_cap: 150` 은 config.
- `powerautomate/`·`docs/배포가이드.md`: `git log --all` 이력 0건.
- 테스트 수: `NC_NO_SCHEDULER=1 python -m pytest --collect-only -q` → 2,410 collected (실행은 안 했다 — 코드 변경 없음).
- 감정평가서: 커밋 `f1f202d`(09-10) "차단되던 KAPA iframe 뷰어 → 정직한 법원경매정보 딥링크 안내".

문서 기준(라이브 미확인 — 지시상 외부 요청·ssh 금지):
- 서버 사양·도메인·매일 06:30: `docs/DEPLOY_AWS.md`, README '운영 배포', 백로그 KCAR-1 의 '매일 06:32'.
- 엔카 407 차단과 터널 구조: `docs/HOME_TUNNEL.md`. 지금 터널이 살아 있는지는 보지 않았다.

확인 못 한 것:
- `capture/` 내용: 읽기 권한이 거부됐다(비밀 폴더). 그래서 '복사 3종 세트 규약이 유효하다'는 '그대로 유효한 것'에 넣지 않았다.
  README 는 "법원경매·엔카·케이카 모두 캡처 없이 실측 재현으로 진행됨"이라 적는다.

## 3. 대조 중 본 것 — Steward 판단 거리 (초안에는 넣지 않음)

1. **CLAUDE.md 도 같은 낡음을 갖고 있다.** '프로젝트 개요'가 여전히 "실운영 수집: Power Automate", "저장소: SharePoint (목록 7종)"로 시작한다.
   아래에 '아키텍처 변경' 주석이 붙어 있다. 그러나 '디렉터리' 표의 `powerautomate/` 는 실재한 적이 없다. CLAUDE.md 는 Steward 파일이라 손대지 않았다.
2. **README 에 낡은 줄이 더 있다.** 'L4 감정평가서 PDF ⏳ 진행예정'은 PS-10·`f1f202d` 로 딥링크 안내가 확정됐다.
   '테스트 94개 통과'는 지금 2,410 수집이다. 'K' 행은 작업 트리에서 이미 고쳐져 있다(미커밋).
3. **죽은 산정 값 두 개가 코드를 읽는 새 세션도 속인다.** config `platform_weight.kcar: 0.95` 와 `calculator.py` 모듈 docstring 의 "케이카 0.95"가 남아 있다.
   `accident_depreciation_rate.minor: 0.05` 도 파서가 `minor` 를 만들지 않아 쓰이지 않는다.
   값을 지우거나 "미사용" 주석을 다는 것은 결과에 영향이 없다(위 §2 경로 근거). 그래도 산정 파라미터라 Steward 결정으로 둔다. 티켓 후보.
4. **C.4-2 글자와 어긋나는 대기 하나.** `courtauction_list.warmup` 은 두 GET 사이를 2초만 쉰다(`time.sleep(2)`). 첫 커밋 `d4cc3dd` 부터 그랬다.
   뒤따르는 목록 요청은 5초를 기다린다. "모든 외부 요청 전 5~10초"를 글자 그대로 지키려면 5초로 올려야 한다(강화 방향). 티켓 후보 — 이번 지시는 저장소 수정 금지라 고치지 않았다.
5. **하드캡 일부가 코드 상수다.** `DAILY_ANALYZE_CAP = 80`·`max_pages=25`·`max_requests=300`, 그리고 `requery_daily_cap` 은 config 키가 없다.
   화물 취득세 `ACQ_TAX_COMMERCIAL = 0.05`·신뢰도 구간 `CONF_CUTOFFS` 도 코드에 있다. config 단일 진실원천 원칙과 부분적으로 어긋난다. 외부화 후보.
6. **`docs/DEPLOY_AWS.md` STEP 8** 은 'DuckDNS 서브도메인'과 `naechaget.co.kr` 을 한 줄에 섞어 쓴다. 도메인 이력이 문서에서 불분명하다. 라이브 확인은 이번 범위 밖이다.

## 4. 스키마 변경

없음. 코드·템플릿 dict 키·DB 스키마를 건드리지 않았다. frontend-engineer 에게 넘길 변경 명세도 없다.
