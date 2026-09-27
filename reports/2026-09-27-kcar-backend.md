---
order: 2026-09-27-12
from: backend-engineer
ticket: KCAR-1
result: needs-owner
verified: 재현
handoff: []
---

# KCAR-1 · 케이카 복구 경로 기술 검토 (코드 수정 없음)

2026-09-27 · backend-engineer · 기준 커밋 `c7d38d0`.
이번에 읽은 파일(`web/service.py`·`web/app.py`·`web/db.py`·`web/ops_health.py`·`src/collect/kcar.py`·`src/collect/encar.py`·`config.yaml`)은 작업트리에서 HEAD 와 같다.
**코드·설정·DB 수정 0건 · 외부 요청 0건 · 서버 접속 0건 · 스키마 변경 없음.**

## [요약]
1. **서버에서 케이카는 매일 1회, 브라우저를 띄우는 단계에서 실패한다.**
   - 시점은 06:30 매일 갱신 안의 '0표본 재조회' 단계다.
   - 외부 요청을 보내기 전에 실패하므로 케이카·엔카 쪽 부하는 없다. 기존 케이카 값도 **보존**된다.
   - 부작용은 두 가지다.
     - 실패할 때마다 Playwright 드라이버 프로세스가 **남는다**. 로컬 재현 결과 1회당 node 1개, Windows 기준 약 110MB다. 서버에서는 확인하지 못했다.
     - 관리자가 [분석]을 누를 때마다 엔카 요청 1회가 결과 없이 소모된다.
2. **더 급한 것은 복구와 상관없는 '블렌드'다.**
   - 공개 입찰예정 383건 가운데 **23건**이 09-05 에 받은 케이카 값을 25~33% 비중으로 섞고 있다. 그 값의 표본은 **2~3건**뿐이다.
   - 이 때문에 시세는 중앙값 70만(5.9%), 최대 307만(23.2%) 달라진다.
   - 실사용 손익분기(max_bid)는 중앙값 +60만, 최대 +270만 달라진다.
   - **판정 2건은 이 값 때문에 한 단계 느슨하게 나간다.**
   - 케이카 값이 얼마나 오래됐는지 확인하는 코드는 어디에도 없다.
3. **케이카 교차검증은 지금까지 한 번도 판정을 내지 못했다.**
   - 라이브 DB 전체에서 케이카 표본은 **최대 3건**이다(111행: 1건 47·2건 40·3건 24).
   - 교차검증은 표본 5건 이상일 때만 판정하는데, 여기에 닿은 적이 없다(agree 0·diverge 0).
   - 지금 수집 방식으로 되살리면 신뢰도에는 효과가 없고, 표본 2~3건짜리 블렌드만 돌아온다.

→ **기술 권고**
- 지금 할 일: **(e) 중지 + 신선도 게이트(N=7) + 드라이버 누수 수정**.
- 복구를 원하면 **(d) 집 PC 실행**만 후보로 둔다. 다만 만들기 전에 집 PC 에서 1회 측정(승인 필요)해 표본 5건에 닿는지부터 확인한다.
- (a)(b)(c)는 권하지 않는다. 이유는 세 가지다: t3.micro 1GB 메모리, AWS IP 차단 전례, §2 의 C.4 결함.

## 측정 조건 (모든 수치 공통)
- **DB**
  - Steward 사본 `live_2026-09-27.db`(md5 `a9882ae202bc794cabf7d8cebb451db2`, 08:39)를 내 scratchpad `kcar_be/` 로 한 번 더 복사해 썼다. 원본은 건드리지 않았다.
  - 앱 코드로 계산할 때는 `DATA_DIR=…/kcar_be/data` 로 `web.db.DB_PATH` 를 사본에 돌렸다. 스크립트 안에서 assert 로 경로를 확인했다.
- **"오늘"** = 2026-09-27(`date('now','localtime')`).
- **입찰예정 모수 두 가지**
  - ⑴ `sale_date >= 오늘`: **425건**. Steward 수치와 같다.
  - ⑵ 공개 목록과 같은 조건 `db.list_vehicles(upcoming_days=365, hide_incomplete=True)`: **383건**.
  - 케이카 관련 수치(43·23건 등)는 두 모수에서 **같다**.
- **로컬 재현 스크립트**는 모두 네트워크를 쓰지 않는다. 가짜 page·세션을 쓰거나 launch 를 예외로 바꿔 끼웠다. 목록은 §7.

## 1. 실패 경로 (질문 1)

### 1-1. 누가 부르나 — 서버 매일 실행
호출 순서는 다음과 같다.
1. `_scheduler_loop` → `start_daily`(**실행마다 새 스레드**) → `daily_update`
2. 엔카가 blocked 가 아니면 → `requery_missing_market`
3. → `recompute_all_market(run_id=None, finalize=False, targets=0표본 물건, max_requests=requery_daily_cap(기본 20))`
4. `kcar_on`(`kcar.ENABLED and kcar_cross_enabled`)이면 → `kcar.new_session()`
5. → `KcarSession.__init__` 의 `chromium.launch(channel="chrome")` 에서 예외
6. → `record_kcar_health("error", …)` → `ks=None` 으로 엔카만 가지고 계속 진행

**`def kcar_crosscheck` 는 매일 실행에서 불리지 않는다.**
- 호출처는 둘뿐이고, 둘 다 관리자 버튼이다.
  - `analyze_single`(POST `/vehicle/{vid}/analyze`)
  - POST `/vehicle/{vid}/crosscheck`
- `daily_update` 의 분석 단계는 `_analyze_item` 을 직접 부른다. 그 안에는 케이카 호출이 없다. grep 결과, service.py 의 kcar 참조는 위 경로들뿐이다.

**라이브 증거**
- settings `kcar_health_at` = 2026-09-27 06:32:54. runs #78(06:30:53~06:37:56) 실행 중이다.
- 메시지: `Error: BrowserType.launch: Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome` + `Run "playwright install chrome"`.

### 1-2. 몇 번 시도하나 — 실행당 1회
- 세션 생성은 `recompute_all_market` 에서 그룹 루프 **전에 한 번**만 한다.
- 실패하면 `ks=None` 이므로, 그룹마다 `_kcar_cross_live` 는 저장값 재적용 분기(`_reapply_stored`)만 탄다.
- 대상이 0건이어도 세션 생성은 시도한다. `kcar_on` 검사가 그룹핑 뒤에 있고 대상 수와 무관하기 때문이다.
- 관리자 경로는 클릭 1회당 1회다.

### 1-3. 부작용
| 항목 | 확인된 사실 | 근거 |
|---|---|---|
| 외부 요청 | 케이카 0건. 브라우저가 뜨지 않는다 | 실패 지점이 launch |
| 파이프라인 시간 | runs #77·#78 모두 약 7분, status done. 케이카 단계가 흐름을 막지 않았다. launch 실패 자체는 로컬 재현에서 수 초 이내(서버는 측정 안 함) | runs 표 |
| **드라이버 누수** | `KcarSession.__init__` 는 `sync_playwright().start()` 뒤 launch 가 실패해도 `_pw.stop()` 을 부르지 않는다. 로컬(Windows, Playwright 1.60.0)에서 새 스레드로 3회 실패시키자 **node.exe 3개가 남았다**(각 RSS 약 110MB). `stop()` 을 부른 대조군은 0개. 같은 스레드에서 두 번째로 시도하면 다른 오류(`It looks like you are using Playwright Sync API inside the asyncio loop`)가 난다 | `leak_check.py`·`leak_fixed_check.py` |
| 서버에서의 누수 | **미검증**(ssh 금지). 매일 실행이 새 스레드라 하루 1개씩 쌓일 것으로 **추정**. `deploy/vm_setup.sh` 유닛에 KillMode 가 없어 systemd 기본값(control-group)이 적용되므로, 서비스를 재시작하면 정리될 것으로 **추정**. 1GB 서버에서는 무시할 크기가 아니다 | 유닛 정의 |
| 헛도는 엔카 요청 | `kcar_crosscheck` 는 **엔카를 먼저 다시 조회**하고 그 뒤에 `kcar.new_session()` 을 부른다. 그래서 관리자 [분석] 1회마다 엔카 요청 1회(+5초)가 결과 없이 소모된다 | `crosscheck_order_check.py`: 케이카 실패 전 엔카 호출 1회 |
| 상태 기록 | 매일 경로는 `error` 를 기록한다(09-23 보강분). 반면 POST `/vehicle/{vid}/crosscheck` 는 `record_kcar_health` 를 부르지 않는다 | `app.py` `crosscheck` |

### 1-4. 실패가 기존 kcar_median 을 지우나 — **보존한다**
- **매일 경로**: `ks=None` 이면 `_reapply_stored` 를 탄다.
  - 저장된 표본이 `min_sample_count`(5) 이상일 때만 저장값으로 교차상태를 다시 계산해, **같은 값**을 다시 쓴다.
  - 5 미만이면 `{}` 를 돌려주므로 케이카 열을 건드리지 않는다.
  - 게다가 `requery_missing_market` 의 대상은 `median_price` 가 없는 물건뿐이다. 케이카 값이 있는 물건은 전부 `median_price` 가 있다(케이카 교차검증의 전제). 따라서 **매일 실행은 케이카 값이 있는 물건을 아예 건드리지 않는다.**
- **관리자 경로**: `kcar_crosscheck` 는 DB 에 쓰기 전에 예외로 빠진다.
  - 재현: 2026타경10111_1 의 kcar_median·kcar_sample·kcar_checked_at·upper_bid·analyzed_at 이 실행 전후 동일했다.
- **목록 갱신**: `db._LISTING_KEEP` 에 케이카 5열이 들어 있어 보존된다.
- **덧붙여 확인한 사실 — 타임스탬프 누락**
  - `_kcar_cross_live` 는 라이브 조회에 성공하면 kcar_median 은 쓰지만 **kcar_checked_at 은 쓰지 않는다**.
  - 지금은 라이브 조회가 한 번도 돌지 않아서 어긋난 행이 0건이다(kcar_median 있음·checked_at 없음 = 0).
  - 그러나 복구하는 순간 타임스탬프가 값의 나이를 거짓으로 말하게 된다. §3 의 게이트보다 먼저 고쳐야 한다.

## 2. 선택지별 기술 평가 (질문 2)

### 먼저 — 모든 복구 경로(a~d)에 공통인 결함 (C.4 관련)
코드 읽기와 네트워크 없는 재현으로 확인한 사실이다.

1. **요청 상한이 실패한 시도를 세지 않는다 (C.4-1).**
   - `_kcar_cross_live` 는 `ks.search` 가 **성공한 뒤에만** `kreq["n"] += 1` 을 한다.
   - 재현(`cap_count_check.py`): 상한 cap=3 으로 두고 8개 그룹을 모두 타임아웃시켰다. 실제 시도는 8회, kreq n 은 0 이었다.
   - 실패한 시도도 페이지를 불러오는 외부 요청이다.
2. **케이카에는 '비정상 3회 연속이면 중단'이 없다 (C.4-5).**
   - 엔카 루프에는 `consecutive_fail` 이 있다.
   - 케이카는 차단이 아닌 예외가 나면 `kcar.search` 결과 캐시를 빈 값(`kcache[ckey]=[]`)으로 두고 그냥 넘어간다.
   - 결국 상한은 그룹 수뿐이다. 수동 재교정(`/recompute-all`)이면 전체 그룹이다.
3. **메인 페이지가 403/429 면 차단으로 알아채지 못한다 (C.4-5).**
   - `kcar.search` 의 차단 판정(`if blocked: raise …차단…`)은 `try/finally` 뒤에 있고, CAPTCHA 문구 검사는 try 블록 끝에 있다.
   - 검색창(`get_by_placeholder(SEARCH_PLACEHOLDER).wait_for`)이 뜨지 않으면 타임아웃 예외가 먼저 튀어서, 두 판정 어디에도 닿지 않는다.
   - 재현(`block_flow_check.py`, 가짜 page): 메인 문서가 403 이든 429 든 타임아웃 예외가 났고, `_is_block` 은 False 였다.
   - 재현에서는 타임아웃 대역 예외를 썼다. 실제 Playwright TimeoutError 도 `response` 속성이 없고 메시지에 '차단'이 없으므로 `_is_block` 결과는 같다(코드 읽기).
4. **관리자 경로는 차단을 'skipped'(정상)로 기록한다.**
   - `kcar_crosscheck` 는 케이카 조회 예외를 전부 `{"ok": False, "msg": "케이카 조회 실패…"}` 로 삼킨다.
   - `analyze_single` 은 ok 가 아니면 `skipped` 를 남긴다.
   - ops_health ④ 는 skipped 를 실패로 보지 않는다.
5. **'ok' 를 너무 일찍 기록한다.**
   - `recompute_all_market` 은 브라우저가 **뜨기만 하면** `record_kcar_health("ok")` 를 남긴다.
   - 검색이 전부 빈손이어도 ok 다. 빈손은 `reached=False`/`single` 로 조용히 처리된다.
6. **`KcarSession.__init__` 드라이버 누수** (§1-3).

→ 1~3 때문에 지금 코드는 C.4 의 "하드캡·차단 시 중단"을 **이미** 지키지 못한다. 어느 복구든 이 결함을 먼저 고친 뒤에야 최초 실행 승인을 올릴 수 있다. 수정은 전부 강화 방향이며 완화는 없다. 예상 0.5일 + 테스트(추정).

### 평가표
| | (a) EC2 에 Google Chrome | (b) 번들 Chromium | (c) 집 회선 프록시 | (d) 집 PC 실행 → 서버 반영 | (e) 중지 + 게이트 |
|---|---|---|---|---|---|
| 코드 변경 | 없음(공통 결함 수정은 별도) | launch 채널을 config 로 뺀다(1곳) | (a 또는 b) + `KCAR_PROXY` 로 launch 에 `proxy=` 전달 + `home_proxy.py` 허용목록 수정 | 신규 3종(대상 내보내기·집 실행기·서버 반영 스크립트) + 예약작업 | config 2줄 + `_blend_ok`·`_kcar_cross_live`·ops_health ④ |
| 서버 작업 | `sudo … playwright install --with-deps chrome`(구글 apt 저장소가 추가됨) | 번들 브라우저가 있는지 확인, 없으면 `playwright install --with-deps chromium` | (a 또는 b) + systemd drop-in 에 `KCAR_PROXY` | 없음(반영 스크립트 실행용 ssh/scp 만) | 배포 1회 |
| 예상 시간(추정) | 설치 10~20분 + 공통 결함 0.5일 | 0.5일 + 공통 결함 0.5일 | 1~1.5일 + 발견 실행 | 2~3일 | 0.5~1일 |
| 실패 위험 | 높음 | 높음 | 중~높음 | 중 | 낮음 |
| C.4 | 공통 결함 수정 후 충족 가능. **최초 실행 승인 필요**(새 출발지 = AWS IP) | 같음 | 같음 + 허용목록 확대 | 같음(같은 `kcar.search` 사용). 첫 자동 실행 승인 필요 | 외부 요청 0 |
| 되돌리기 | apt remove + config | config | 환경변수 삭제 + 허용목록 원복 | 예약작업 해제(이미 반영된 값은 게이트가 자동으로 만료) | config 1줄 |

### (a) EC2 에 Google Chrome
- **확인된 사실**
  - 서버는 t3.micro(x86_64, 1GB)다 — `docs/DEPLOY_AWS.md`.
  - Google Chrome 리눅스판은 x86_64 용만 있으므로 설치 자체는 가능하다.
  - 서버에 Playwright 파이썬 패키지와 드라이버는 이미 있다. 오류 문구가 드라이버에서 나왔기 때문이다.
- **위험 ① 메모리**
  - 저장소 문서 두 곳이 이미 경고한다.
    - `DEPLOY_AWS.md`: "케이카 수집은 제가 이 개발환경에서 돌려 DB에 반영 → t3.micro(1GB)로도 웹 서빙 충분"
    - `DEPLOY_ORACLE.md`: "1GB로 케이카 수집엔 부족"
  - 헤드리스 브라우저가 SPA 한 장에 수백 MB 를 쓸 것으로 **추정**한다(미측정). 웹 서빙과 같은 머신이다.
- **위험 ② IP**
  - 엔카가 같은 EC2 IP 를 407 로 막은 전례가 있다(`docs/HOME_TUNNEL.md`).
  - 케이카가 데이터센터 IP 를 어떻게 다루는지는 **미검증**이다.
  - 막힌다면 위 결함 3·5 때문에 **조용히 빈손**이 될 가능성이 높다.
- **위험 ③ 운영**
  - 구글 apt 저장소가 추가되면 자동 업데이트 경로가 생긴다.
  - apt 자동 업그레이드가 서비스를 끊은 전례가 2회 있다(`_scheduler_loop` 위 주석, 09-14·09-17).
- **승인 범위**
  - `kcar.py` docstring 에는 "실행은 사용자 환경(터미널)에서 이뤄진다(엔카와 동일 강행 승인)"라고 적혀 있다.
  - 서버에서 실행하면 그 범위를 벗어난다. 따라서 C.4-6 최초 실행 승인과 준법 재확인이 필요하다. 준법 판단은 compliance-officer 몫이다.

### (b) 번들 Chromium (headless)
- **chrome 채널을 고른 이유 — 코드·문서에 근거가 없다(확인된 사실).**
  - `kcar.py` 에는 채널 선택 이유를 적은 주석이 없다. git 이력으로는 첫 커밋(`ffac48e`, 08-23 "누락 파일 추가")부터 이 상태다.
  - 오히려 반대 근거가 둘 있다.
    - README 설치 절: "`python -m playwright install chromium` 또는 시스템 Chrome(`channel="chrome"`)"
    - `deploy/vm_setup.sh` 는 **번들 chromium 을 설치**한다.
  - 즉 배포 스크립트가 설치한 브라우저와 코드가 찾는 브라우저가 어긋나 있다.
  - 집 PC 에 크롬이 이미 있어서 편의상 고른 것으로 **추정**한다.
- **봇 탐지**
  - 지금 코드도 **이미 헤드리스**다(`launch()` 기본값 headless=True).
  - 바뀌는 것은 두 가지다.
    - 바이너리: 크롬 브랜드 → 크로미엄
    - 헤드리스 방식: 번들 기본값은 headless shell 이고, `channel="chromium"` 이면 신형 헤드리스다(Playwright 1.49+ 동작, 서버 버전은 미확인).
  - 탐지 차이가 생기는지는 **근거가 없어 추정할 수 없고, 검증도 안 됐다**. 코드에 있는 단서는 "reCAPTCHA v3 배지가 페이지에 늘 떠 있다"는 주석 하나뿐이다.
- 서버에 번들 브라우저가 실제로 있는지는 **미검증**이다. `requirements.txt` 가 playwright 버전을 고정하지 않으므로, vm_setup 이후 버전이 올라갔다면 브라우저 리비전이 안 맞을 수 있다.
- 메모리·IP·C.4 위험은 (a)와 같다. 구글 apt 저장소가 생기지 않는다는 점만 낫다.

### (c) 집 회선 터널로 내보내기
- **엔카가 실제로 이 경로를 타는 방식(확인된 사실)**
  - `encar.new_session()` 은 환경변수 `ENCAR_PROXY` 가 있을 때만 그 값을 `requests.Session.proxies` 에 넣는다.
  - 서버 systemd drop-in 이 `ENCAR_PROXY=http://127.0.0.1:18080` 을 지정한다. 이 포트는 역방향 `ssh -R` 로 집 PC 의 `tools/home_proxy.py` 에 연결된다.
  - `home_proxy.py` 는 127.0.0.1:8888 에서 **CONNECT 요청만** 받고, 허용목록은 `ALLOWED_SUFFIXES = ("encar.com",)` 이다.
  - 케이카는 브라우저로 요청하고 `requests` 를 쓰지 않으므로 이 경로를 **자동으로 타지 않는다.**
- **필요한 것**
  - ⑴ `KcarSession.__init__` 에서 별도 환경변수 `KCAR_PROXY` 를 읽어 `launch(proxy={"server": …})` 로 넘긴다.
  - ⑵ `home_proxy.py` 허용목록에 kcar.com 을 추가한다.
    - 그런데 SPA 는 kcar.com 밖의 호스트(CDN·분석·reCAPTCHA 등)도 부른다. 그 목록은 **저장소 어디에도 없다**.
    - C.4-3(추측 금지)에 따라 집 PC 에서 발견 실행을 먼저 해야 한다.
    - 허용목록 밖의 호스트는 프록시가 403 으로 막는다. 그러면 페이지가 깨지거나 reCAPTCHA 가 실패할 수 있다(추정).
    - kcar.com 만 프록시로 보내는 PAC 방식도 가능은 하지만, 요청마다 IP 가 섞인다. 그 효과는 미검증이다.
- **전제 조건**: (a) 또는 (b)가 먼저 되어 있어야 한다. 따라서 EC2 메모리 위험은 그대로 남고, IP 위험만 줄어든다. 집 PC 가 켜져 있어야 한다는 의존은 엔카와 같다.
- **보안 자세 변경**: `HOME_TUNNEL.md` 의 설계 전제 "encar.com 허용목록이라 다른 용도로 쓰이지 않는다"가 넓어진다.

### (d) 집 PC 에서 케이카만 돌리고 결과를 서버로
- **전제(확인된 사실)**
  - 집 PC 에 Google Chrome 이 있다(`C:\Program Files\Google\Chrome\Application\chrome.exe`).
  - 원래 설계가 이것이었다(`kcar.py` docstring, 위 `DEPLOY_AWS.md` 인용).
  - 로컬 DB 의 max(kcar_checked_at) = 2026-09-05 23:10:39 로 라이브와 같다. 그래서 09-05 값은 집 PC 에서 만든 값이 DB 이관으로 올라갔을 것으로 **추정**한다.
- **지금 서버에 입력 경로가 없다(확인된 사실).**
  - POST 라우트는 daily settings·run-now·analyze·recompute·crosscheck·actual·run·reanalyze·results/run-now·recompute-all 이 전부다. 업로드·수신용 라우트는 없다.
  - 유일한 선례는 사진 순서다. 집 PC 에서 `scripts/photo_classify.py export-patch` 로 JSON 을 만들고, scp 로 옮긴 뒤, 서버에서 `scripts/apply_photo_order_patch.py` 를 돌린다.
- **필요한 것(위 선례를 따른 설계안)**
  1. **서버에서 대상 내보내기**: 입찰예정이면서 엔카 시세가 있는 물건의 키워드·연식·하이브리드 여부를 뽑는다.
     - 연료는 서버의 `data/<폴더>/appraisal.txt` 에 있다.
     - 집 PC 로컬 DB 는 09-17 에 멈춘 개발 사본이라 쓰면 안 된다(로컬 max(collected_at) 2026-09-17 19:03).
  2. **집 PC 실행기**: (키워드·연식·하이브리드) 조합당 1회 `kcar.search` 를 부른다. 런 상한과 일일 상한을 두고, 공통 결함 수정도 포함한다.
  3. **전송**: 정규화한 원 매물 목록을 패치 파일로 만들어 scp 로 보낸다.
  4. **서버 반영 스크립트**: 물건별로 `summarize` + `cross_source_check` 를 **서버의 현재 엔카 시세**로 계산한다. 케이카 열과 `kcar_checked_at`(= 집에서 가져온 시각)만 쓴다.
  - `_kcar_cross_live` 를 "가져오기"와 "적용" 둘로 나누면 로직이 한 곳에 남는다.
- **설계 결정 1개**
  - 두 소스를 비교하는 조건(`kstats.tier_level <= stats.tier_level`)에 엔카 tier 가 필요한데, DB 에 저장돼 있지 않다.
  - 방법은 둘이다: 반영할 때 엔카를 다시 조회하거나(서버 엔카 상한 안에서), tier 열을 추가한다(ALTER 가드).
  - 오너가 아니라 Steward 와 내가 정할 일이다.
- **위험**
  - 집 PC 에 의존한다. 엔카 터널과 같은 조건이다.
  - 실행 시간이 길다. 검색 1회에 고정 대기만 7.1초(2.6+1.5+1.2+1.8, 6초 스로틀은 이 안에 흡수된다)이고, 여기에 네트워크 대기(goto 최대 30초·검색창 최대 15초·networkidle 최대 15초)가 붙는다. 60조합이면 약 10~70분으로 추정한다.
- **가치 의문 (가장 중요)**
  - 라이브 DB 의 케이카 표본은 전부 1~3건이다(111행). 교차검증 최소치 5건에 한 번도 닿지 않았다.
  - 원인은 두 가지가 겹친 것으로 **추정**한다.
    - 첫 페이지만 가로채는 수집: `search` 가 그리드 응답 하나만 고른다.
    - 연식±1·주행±30%·연료·트림 필터.
  - 이 원인을 고치지 않으면 (d)를 만들어도 신뢰도 효과는 0 이고, 표본 2~3건짜리 블렌드만 돌아온다.
  - → 만들기 전에 **집 PC 에서 물건 3건으로 1회 측정**한다(요청 3회, 승인 필요). `kcar_crosscheck` 가 돌려주는 kcar_found·kcar_matched·kcar_sample 을 본다.

### (e) 중지
바꿀 자리(앵커)는 다음과 같다.
1. **`config.yaml` `kcar_cross_enabled: false`**
   - `analyze_single`·`recompute_all_market` 의 케이카 분기가 꺼진다. 브라우저 기동·누수·헛도는 엔카 요청이 모두 멈춘다.
   - 단 POST `/vehicle/{vid}/crosscheck` 는 `kcar.ENABLED` 만 보므로 **계속 돈다**. 서버에서 막으려면 `kcar_crosscheck` 첫머리에 같은 설정 검사를 넣는다. 수동 버튼은 템플릿에서 PS-02 로 이미 빠졌다.
2. **신선도 게이트** — §3.
3. **ops_health ④**
   - `recompute_all_market` 에서 `kcar_on` 이 거짓이면 `record_kcar_health("disabled", "kcar_cross_enabled=false")` 를 남긴다. 매일 06:30 갱신이 이 함수를 부르므로 상태가 매일 새로 기록된다.
   - `ops_health.evaluate` 의 ④ 첫머리에 `k_state == "disabled"` 분기를 넣는다.
     - 상태: `ok`
     - 값: `중지(의도)`
     - 설명: "설정으로 끔 — 산정은 엔카 단독, 오래된 케이카 값은 블렌드하지 않음"
   - 새 상태('off')는 권하지 않는다. STATE_ORDER·일일 리포트·사내 대시보드 렌더러까지 손대야 하기 때문이다. 기존 'ok' 를 재사용한다.
   - 스냅샷에 새 키는 필요 없다. `tools/daily_ops_report.py` 가 이미 settings `kcar_health_state` 를 읽는다.
4. **`KcarSession.__init__` 누수 수정**
   - launch 가 실패하면 `self._pw.stop()` 을 부른 뒤 예외를 다시 던진다.
   - 중지하더라도 넣는다. 다시 켜는 날 또 새기 때문이다.

- C.4: 외부 요청 0. 되돌리기: config 1줄.

## 3. 신선도 게이트 — 복구와 무관하게 필요한가 (질문 3): **필요하다**

### 3-1. 지금 케이카 값의 나이를 보는 코드 — 없다(확인된 사실)
`kcar_checked_at` 을 읽는 곳을 전부 찾았다(grep, tests 제외).
- ops_health ④: DB **전체 max** 하나만 본다. 물건별이 아니다.
- `supply_snapshot`·`tools/daily_ops_report.py`: 같은 max 값.
- `PRIVATE_FIELDS`: 공개 화면 차단용.
- 관리자 상세 템플릿: 날짜 표시용.

산정 쪽(`effective_median`·`_blend_ok`·`_reapply_stored`·`market_provenance.cross_n`)은 나이를 **보지 않는다**.

### 3-2. 왜 복구와 무관한가
- **지금 23건이 22일 된 값을 섞고 있다**(요약 2번). 그중 판정이 바뀌는 2건은 아래와 같다. 계산 함수는 `bid_state`, 저장 upper_bid 는 그대로 둔 조건이다.

  | 물건 | 기일 | 엔카 / 케이카(표본) | 블렌드 있음 | 게이트 후 |
  |---|---|---|---|---|
  | 2025타경53211_1 말리부 2.0 TURBO 2018 | 10-01 | 750만 / 1,060만(2) | usepick "이득 불확실 — 오차 범위 안" · max_bid 620만 | over_market "예상 경쟁가가 상한선 초과" · 550만 |
  | 2026타경10111_1 카니발 2019 | 09-28 | 1,290만 / 1,890만(3) | over_market · max_bid 1,200만 | blocked "이번 회차 입찰 부적합" · 1,030만 |

- **게이트 효과는 한쪽 방향이 아니다.**
  - 23건 중 18건은 게이트로 시세가 내려간다.
  - **5건은 오히려 올라간다**. 케이카가 엔카보다 낮았던 물건이다. max_bid 기준으로 최대 70만이 오른다.
  - 따라서 "게이트 = 무조건 보수적"이 아니다. 오너에게 보고할 때 이 점을 함께 올려야 한다.
- **복구해도 매일 경로는 케이카 보유 물건을 다시 조회하지 않는다**(§1-4).
  - 재조회 대상은 시세가 없는 물건뿐이고, 분석 단계에는 케이카가 없다.
  - 게이트가 없으면 복구한 값도 같은 식으로 늙는다.
- **공개 화면에도 영향이 있다.**
  - 공개 상세·리포트에 "2차 소스 2~3건 반영"이 찍힌다(`market_provenance.cross_n` → detail·report).
  - 이 23건은 엔카 쪽도 09-05 분석이라 이미 '근거 약함'(stale, days 22)으로 표시되고 있다. 날짜가 숨겨진 것은 아니다.
  - 그래도 표본 2건짜리 값이 25% 비중으로 숫자를 움직이는 문제는 그대로 남는다.

### 3-3. 넣을 자리
1. **`_blend_ok(v)`**
   - `effective_median` 과 `market_provenance.cross_n` 이 **둘 다** 이 함수를 거친다. 그래서 한 곳만 고치면 화면과 산정이 같이 바뀐다.
   - 렌더 시점에 계산하므로 재분석 없이 즉시 반영된다.
   - 규칙:
     - `kcar_checked_at` 이 없으면 블렌드하지 않는다(**fail-closed**). 라이브에 kcar_median 은 있는데 시각이 없는 행이 0건이라 부작용은 없다.
     - 나이가 N 일을 넘으면 블렌드하지 않는다.
2. **내부 호출 두 곳이 `effective_median({...})` 에 `kcar_checked_at` 을 넘기게 한다.**
   - `recompute_all_market`: 라이브면 지금 시각, 재적용이면 저장값.
   - `kcar_crosscheck`: 지금 시각.
   - 넘기지 않으면 fail-closed 때문에 새 값도 섞이지 않는다.
3. **`_kcar_cross_live` 라이브 분기가 `kcar_checked_at` 을 쓰게 한다**(§1-4 에서 덧붙여 확인한 사실).
4. **`_reapply_stored` 에도 같은 나이 검사를 넣는다.**
   - 낡은 값으로 agree 를 다시 만들어 신뢰도 상한 88→96 을 푸는 길을 막는다.
   - 지금은 표본 5건 이상인 행이 0건이라 잠재 경로일 뿐이다.
5. **N 은 `config.yaml` 새 키 `kcar_blend_max_age_days` 로 둔다**(단일 진실원천).
   - ops_alert 의 `kcar_stale_days` 는 감시값이라 재사용하지 않고, 값만 맞춘다.

### 3-4. N 후보
| N | 근거 | 지금 데이터에 미치는 효과(오늘 기준) |
|---|---|---|
| **7 (권고)** | `ops_alert.kcar_stale_days: 7` 과 같다 → "경보가 뜨면 블렌드도 이미 멈춰 있다". 감시와 산정이 다른 말을 하지 않는다 | 23건 전부 블렌드 해제 |
| 14 | `market_provenance` 가 엔카 시세를 14일부터 '근거 보통'으로 내린다(하드코딩) | 23건 전부 블렌드 해제 |
| 30 | 수집 창 `within_days=30` | 09-05 값 22건이 **10-05 까지 계속 섞인다**. 23건의 기일이 09-28~10-07 이라 사실상 보호 효과가 없다 |

- 중고차 시세가 7일·14일 동안 얼마나 움직이는지는 저장소에 측정이 없다. 그래서 7 과 14 사이는 데이터로 가를 수 없다.
- 7 을 권하는 이유는 가격 변동이 아니라 **감시 임계와의 일치**다.
- (d)로 되살린다면, 7일 안에 전 대상을 한 바퀴 도는 일일 상한이 필요하다(조합 수 × 10~70초).

### 3-5. 필요한 테스트
- `_blend_ok`: 나이 N-1 → True, N+1 → False, 시각 없음 → False, 날짜 형식 깨짐 → False.
- `effective_median`·`market_provenance.cross_n`: 값이 낡았으면 median_price 를 그대로 쓰고 cross_n 은 0.
- config 에서 N 을 바꾸면 결과가 바뀐다(하드코딩 방지).
- `_kcar_cross_live`: 라이브 분기가 kcar_checked_at 을 쓴다(가짜 ks). 재적용 분기는 낡은 값으로 agree 를 만들지 않는다.
- `recompute_all_market`·`kcar_crosscheck` 의 내부 블렌드가 새 값은 섞는다(fail-closed 회귀 방지).
- ops_health: `disabled` 면 ④ 가 warn 이 아니다. 다시 켜서 error 가 나면 기존대로 warn.
- `KcarSession`: launch 가 실패하면 드라이버 stop 이 불린다(sync_playwright 가짜).
- 공통 결함 1~3: 실패한 시도도 상한에 세어지고, 3연속 실패하면 멈추고, 메인 문서 403/429 가 차단으로 판정된다(가짜 page).
- **기존 픽스처 갱신**: `kcar_checked_at` 없이 dict 를 만들고 블렌드를 전제하는 테스트 5개다(grep 기준).
  - `test_price_consistency.py`·`test_market_provenance.py`·`test_accuracy_price_band.py`·`test_render_smoke.py`·`test_panel_r3_market_label.py`
  - 시각은 `date.today()` 기준 상대값으로 넣어야 날짜가 지나도 테스트가 깨지지 않는다.

### 3-6. 게이트가 남기는 불일치 하나
- **무엇이 어긋나나**
  - 23건 모두 `analyzed_at == kcar_checked_at`(09-05)이다. 즉 저장된 `upper_bid` 는 **블렌드 시세로** 계산돼 있다.
  - 게이트를 넣으면 화면 시세(렌더 시점 계산)는 내려가는데, `upper_bid`(저장값)는 그대로다.
- **판정에 미치는 영향**
  - `bid_state` 에서 upper 는 `resale` 분기(`exp <= upper`)에만 쓰인다.
  - 23건 중 resale 은 0건이고, upper 가 내려가면 resale 에서 더 멀어질 뿐이다. 그래서 **판정은 위 2건 외에는 바뀌지 않는다**.
  - 다만 관리자 산식 화면의 숫자는 서로 어긋난다.
- **선택지**
  - ① 다음 재분석까지 그대로 둔다.
  - ② 저장 시세로, 외부 요청 없이 재산정하는 1회 스크립트를 돌린다. 기존 `recompute()` 는 요항 원문·사진 수를 넘기지 않아 상태 감가가 빠지므로, 그대로 쓰면 안 된다.

## 4. 기타 확인된 사실 (별도 티켓 후보)
- **블렌드 상수가 코드에 박혀 있다.**
  - `_blend_ok`: 최소 표본 2, 비율 0.5~2.0
  - `effective_median`: 가중 `kn/(kn+6)`, 상한 0.35
  - "산정 상수는 config.yaml" 규칙에 어긋나고, 교차검증 최소 표본 5(`min_sample_count`)와도 다르다.
  - 최소 표본을 5로 맞추면 현재 데이터의 블렌드는 전부 꺼진다. 산정 변경이라 오너 승인 사안이다.
- `config.yaml` 의 `platform_weight.kcar: 0.95` 는 사실상 쓰이지 않는다. 서비스의 `BidInput` 은 전부 `platform="encar"` 다.
- ops_health ④ 설명 "자동 경로가 없어 사람이 돌릴 때만 갱신된다"는 반만 맞다. 자동 경로(재조회→재교정)는 있지만, 그 경로가 `kcar_checked_at` 을 쓰지 않는다.

## 5. 권고와 오너 결정 항목
**기술 권고 (내 자리의 판단)**
1. **지금 (외부 요청 0, 강화 방향)**: (e) 를 한다.
   - `kcar_cross_enabled: false`, 게이트 N=7, `disabled` 신호, 누수 수정, `kcar_crosscheck` 설정 검사.
   - 0.5~1일. `python -m pytest -q` 전체 통과가 조건이다.
2. **복구를 원하면**
   - 공통 결함 1~5 를 먼저 고친다(0.5일).
   - 집 PC 에서 1회 측정해 표본 5건에 닿는지 확인한다(물건 3건·요청 3회, **승인 필요**).
   - 닿으면 (d) 로 간다. 못 닿으면 케이카를 은퇴시킨다. 코드 제거는 그 뒤에 따로 판단한다.
3. **(a)(b)(c) 는 권하지 않는다.**
   - 1GB 서버에 헤드리스 브라우저를 올려야 한다.
   - AWS IP 차단 전례가 있다.
   - 공통 결함 3·5 때문에 막혀도 조용히 빈손이 된다.

**오너 결정이 필요한 것 (나는 실행하지 않는다)**
- **게이트를 넣으면 공개 화면의 수치·판정이 바뀐다.**
  - 23건 시세, 판정 2건, 그리고 5건은 max_bid 가 오른다.
  - 판정 기준 '완화'는 아니지만 판정 표시가 바뀌므로 CLAUDE.md 상 교차검수 대상이다.
- **복구한다면 필요한 것**
  - C.4-6 최초 실행 승인: 외부 요청의 출발지와 자동화 범위가 바뀐다.
  - 서버 설치(a/b/c 의 경우).
  - 준법 재확인. compliance-review 는 케이카 위험을 '높음'으로 두고 "무료 검증 도구로는 현 방식 유지 가능"이라고 적었는데, 지금은 공개 앱이다. 판단은 compliance-officer 몫이다.

이 보고서는 코드·설정·DB 를 하나도 고치지 않았다. **스키마 변경 없음.**

## 6. 확인된 사실 / 추정 / 미검증
- **확인된 사실(재현)**
  - §1 호출 경로, 실행당 1회 시도, 기존 값 보존
  - 드라이버 누수(로컬 Windows), 헛도는 엔카 요청
  - 공통 결함 1~3(가짜 세션으로 재현), 4~5(코드 읽기)
  - DB 수치 전부(사본 기준, '측정 조건' 참조)
  - 서버 입력 경로 없음, chrome 채널 근거 없음, 집 PC 에 크롬 있음
- **추정**
  - 서버 누수가 누적되고 재시작 때 정리되는지
  - 브라우저 메모리 수백 MB
  - 번들 Chromium 과 크롬의 탐지 차이
  - 케이카의 AWS IP 차단 가능성
  - 표본이 1~3건에 머무는 원인
  - 검색 1회 10~70초
  - 09-05 값의 출처(집 PC → DB 이관)
  - 작업 시간
- **미검증 (서버 접근 필요)**
  - 서버에 번들 Chromium 이 있는지, Playwright 버전
  - 서버에 남아 있는 드라이버 프로세스 수(`ps aux | grep -c "[p]laywright"`)
  - 서버 여유 메모리·스왑·디스크

## 7. 재현 방법
- **스크립트** (scratchpad `kcar_be/`, 전부 네트워크 없음)
  - `leak_check.py`(md5 앞 8자리 83752729)
  - `leak_fixed_check.py`(2be43eed)
  - `block_flow_check.py`(1ca9fec3)
  - `cap_count_check.py`(e0f6c98c)
  - `crosscheck_order_check.py`(2acd080e)
  - 실행: 저장소 루트에서 `DATA_DIR=<scratchpad>/kcar_be/data NC_NO_SCHEDULER=1 python <스크립트>`
- **DB 수치**
  - 위 사본에서 대상을 뽑는다: `db.list_vehicles(upcoming_days=365, hide_incomplete=True)` 또는 `select … where sale_date >= date('now','localtime')`.
  - 각 물건을 kcar_median/kcar_sample 을 None 으로 바꾼 사본과 비교한다. 비교 함수: `service._blend_ok`·`effective_median`·`bid_state`·`personal_use_max_bid`·`expected_for`·`market_provenance`.
  - `backtest_stats()` 도 같은 사본 기준이다. `expected_for` 는 23건 모두 변화가 없었다.
