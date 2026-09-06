# MONETIZATION_SPEC — 경매로 내차GET 유료화·격리·인증 설계서

> 이 문서는 **VS Code + Claude Code로 태스크를 하나씩 실행**하기 위한 실행 스펙이다.
> 각 태스크는 독립적으로 구현·검증되도록 쪼개져 있다. **묶어서 시키지 말 것** — 격리 계층이 흐트러진다.
>
> 사용법:
> ```
> docs/MONETIZATION_SPEC.md 를 읽고 TASK-M01만 구현해. 완료 기준을 모두 만족시키고, 끝나면 검증 결과를 보여줘.
> ```
> 실행 순서: **Phase A(M01~M04) → B(M05~M06) → C(M07~M10) → D(M11~M14)**.
> Phase A는 앱이 없어도 지금 서버에 바로 적용 가능하고 나머지가 이 위에 얹힌다. 특히 M01(격리)·M02(유출 테스트)를
> 나중에 하면 이미 짜놓은 응답을 전부 다시 손봐야 한다.

---

## 0. 현재 상태 (2026-09 기준 — Claude Code가 반드시 인지할 것)

- **스택**: FastAPI + Jinja2 **서버렌더**(웹 HTML) + SQLite(`web/db.py`, 테이블 `vehicles`/`runs`/`sale_results`/`settings`). uvicorn 127.0.0.1:8000 + nginx + certbot. AWS EC2(43.202.126.180).
- **앱 형태**: **TWA**(웹을 그대로 감싸는 안드로이드 래퍼). 즉 "앱"이 별도 JSON API를 호출하는 구조가 **아직 아니다** — 앱 = 웹사이트. → 엔카 격리는 **서버 렌더 데이터 계층**에서 한다(§2).
- **이미 있는 것**: 관리자 모드(`web/app.py`의 `is_admin(request)` — `NAECHAGET_ADMIN_KEY` 쿠키, `/admin?key=…`). 현재는 **템플릿에서 `{% if is_admin %}`로 숨김** + 운영 POST 라우트 서버측 403. 엔카 원자료(시세 소스·개별 동급 매물·분포)·운영 도구가 관리자 전용.
- **아직 없는 것**: 사용자 계정/인증, 등급(tier), 결제, 관리자 서브도메인, 데이터 계층 엔카 strip(현재는 템플릿 숨김만 — M01에서 데이터 계층으로 내림).
- **예측 모델(자체 자산)**: `예상낙찰가 = 최저매각가 × 유찰버킷 프리미엄`, LOO MAE 8.7%(`web/service.py: expected_for/expected_band`).

> ⚠️ Claude Code는 각 태스크 착수 전 **실제 스키마를 확인**하라: `PRAGMA table_info(vehicles)`. 아래 필드 목록은 설계 기준 추정이며 실제와 다르면 실제를 따른다.

---

## 1. 원칙 (타협 불가)

1. **유료의 근거는 '자체 자산'으로 채운다 — 엔카가 아니라.** 엔카를 관리자만 본다고 법적 리스크가 사라지지 않는다. 문제는 "누가 보느냐"가 아니라 "robots.txt를 무시한 자동 수집을 **상업 서비스의 가치 기반**으로 쓰느냐"다. 격리는 필요조건이지 충분조건이 아니다. → **2·3단계 유료 기능은 다음 자체 자산으로 구성한다**:
   - 유찰 프리미엄 예측 모델 + 정직 백테스트(MAE 8.7%) — 대체 불가
   - D-3 매각기일 알림
   - **낙찰가 실측 누적 DB**(시간이 쌓일수록 해자↑)
   - 사진 비전 분류 · 감정요항 파싱 · 물건별 11섹션 리포트
2. **등급 판정은 서버에서만.** 앱이 "나 유료야"라고 주장하는 걸 믿지 않는다. 서버가 결제 토큰을 검증해 DB 등급을 정한다.
3. **엔카/케이카 원자료는 UI가 아니라 응답 데이터에서 제거.** 화면에서 숨기면 소스보기·API 직접호출로 새어 나간다. **직렬화/컨텍스트 단계에서 뺀다.**
4. **관리자 진입점을 앱·사용자 도메인에 두지 않는다.** APK는 디컴파일된다. 관리자는 **별도 서브도메인 웹**(`admin.naechaget.co.kr`) + 서버단 보호(IP allow / Basic / SSH 터널).
5. **자체 이메일/비밀번호 인증을 만들지 않는다.** Google Sign-In(Firebase)에 위임 — 해싱·재설정·유출대응을 떠안지 않는다.
6. **인앱 디지털 판매는 Google Play Billing 강제**(수수료 15~30%). 카드/계좌 붙이면 앱 삭제.
7. **신뢰 최우선**([[feedback-data-trust-verification]] 원칙 유지): 없는 데이터 지어내지 않기, 근거·범위·표본 정직 표기.

---

## 2. 엔카 필드 분류 (M01 화이트리스트 기준 — PRAGMA로 검증)

`vehicles` 테이블(그리고 파생 dict)을 세 부류로 나눈다.

### PRIVATE — 비관리자 응답에서 **반드시 제거**(엔카/케이카 원자료·운영값)
```
market_platform, encar_total, sample_count, mean_price, min_price,
market_cv, market_vs_appraisal, comps,
kcar_median, kcar_sample, cross_source_status, cross_source_rel, kcar_checked_at,
actual_price, actual_price_at, repair_cost
```

### BORDERLINE — 노출 여부를 **운영자가 결정**(엔카 파생 '결과값')
| 필드 | 무엇 | 권고 |
|---|---|---|
| `median_price` | 엔카 중앙값(화면엔 '소매 시세') | 소매 차익 표기에 필요. **노출 유지하되 라벨은 '소매 시세'**(브랜드명 금지) 또는 제거 후 소매차익 섹션 자체를 관리자 전용화 — §5에서 결정 |
| `market_confidence`, `market_confidence_label` | 시세 신뢰도 점수/라벨(파생) | 사용자 노출 유지(브랜드 무관) |
| `upper_bid`, `lower_bound`, `breakdown` | 재판매 손익분기(기준시세=median 사용) | 노출 유지 가능(엔카 브랜드 미표기). 단 median 완전 제거를 택하면 이 값도 재검토 |

### PUBLIC — 사용자에게 안전(법원 공개 데이터 + 자체 모델)
```
id, case_no, item_no, court, court_code, location, storage_addr,
maker, model, year, mileage_km, displacement_cc, fuel_code,
appraisal_value, min_sale_price, fail_count, sale_date, sale_time, sale_place,
inspection_to, condition_level, condition_flags, photo_order, photo_count, folder_key, spec_remark,
accident_grade, accident_hits, insurance_history,
judgment, status, auction_result, winning_price, dxdy_history, result_source,
# ※ starred(즐겨찾기)·memo·final_bid(최종입찰가)는 서버 미저장 — 모두 기기 로컬(localStorage)로 이관됨(다중 사용자 안전). DB 컬럼은 레거시 호환용으로 남되 서버가 렌더하지 않음.
# 파생(계산):
expected_win(예상낙찰가=자체 모델), expected_band(보수/균형/공격), dday
```

> `expected_win`은 `최저매각가 × 유찰 프리미엄`이라 **엔카 median에 직접 의존하지 않는다**(소프트캡에서만 median 참조). 자체 모델의 핵심 산출물 → PUBLIC.

---

## 3. 목표 아키텍처

```
naechaget.co.kr          → 일반 사용자(웹/TWA). 응답에 PRIVATE 필드 없음. 등급별 기능 제한.
admin.naechaget.co.kr    → 관리자 웹(운영자만). 엔카 원자료·운영 도구 전체. nginx IP allow / Basic / SSH 터널.
(공유) 같은 FastAPI 앱·같은 SQLite DB. 분리는 '조회 계층'에서. 앱을 나눌 필요 없음.
```

- **인증(사용자)**: 앱에서 Google Sign-In(Firebase) → ID 토큰 → 서버가 `google-auth`로 검증 → `users`에 upsert → 등급 조회.
- **결제**: 앱 Google Play Billing 구독 → 구매 토큰 → 서버 Play Developer API 검증 → **acknowledge(3일 내!)** → 등급 갱신. 해지/환불은 **RTDN(Pub/Sub webhook)** 로 수신.
- **등급 게이팅**: 요청의 사용자 등급을 서버가 판정 → 응답 데이터·기능을 등급별로 필터.

---

## 4. 데이터 모델 (신규 테이블 — M04)

```sql
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,   -- Firebase uid (google sub)
    email         TEXT,
    tier          INTEGER DEFAULT 1,  -- 1 무료 / 2 / 3 (서버 권위)
    tier_source   TEXT,               -- free / play_sub / grant(수동)
    sub_product   TEXT,               -- 구독 상품 id
    sub_expiry    TEXT,               -- 구독 만료(UTC ISO) — 지나면 자동 강등
    sub_state     TEXT,               -- active / grace / on_hold / canceled / expired
    play_purchase_token TEXT,         -- 최신 구매 토큰(RTDN 대조용)
    created_at    TEXT,
    updated_at    TEXT
);
CREATE TABLE IF NOT EXISTS purchases (   -- 결제 감사 로그(멱등·재검증용)
    purchase_token TEXT PRIMARY KEY,
    user_id       TEXT,
    product_id    TEXT,
    state         TEXT,                 -- verified / acknowledged / refunded / canceled
    raw           TEXT,                 -- Play API 원응답(json)
    verified_at   TEXT,
    acknowledged_at TEXT
);
CREATE TABLE IF NOT EXISTS usage_daily ( -- 무료 등급 일일 열람 제한(M11)
    user_id  TEXT, ymd TEXT, kind TEXT, n INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, ymd, kind)
);
```
> `web/db.py`의 `init_db()` 마이그레이션 패턴(누락 컬럼 ALTER)과 동일 스타일로 추가. 기존 `settings` 테이블 재사용 가능.

---

## 5. 기능·등급 매트릭스 (가격은 **임의값 — 조정 필요**)

| 기능 | 1단계(무료) | 2단계 | 3단계 |
|---|---|---|---|
| 물건 목록·상세·사진·경매 달력 | ✅ | ✅ | ✅ |
| 예상낙찰가 열람 | **일 3건 제한** | 무제한 | 무제한 |
| D-3 매각기일 알림 | — | ✅ | ✅ |
| 관심목록 | 제한(예: 5건) | 무제한 | 무제한 |
| 추천 입찰 전략 밴드 | — | 요약만 | ✅ 전체 |
| 리포트 V2(11섹션)·수익 시뮬 | — | — | ✅ |
| 가격(월, 예시) | 0원 | **9,900원** | **19,900원**(임의) |
| 건당 리포트(예시) | — | — | **1,900원** or 보상형 광고 1회 |

- **보상형 광고**(광고 시청 → 리포트/예상낙찰가 1건 해제)는 1~2단계 완충재. 결제 저항 큰 초기에 적합.
- ⚠️ 가격 `3,900/9,900/1,900`(다른 어시스턴트 가정값) 및 위 표는 **경쟁 앱·목표 ARPU 보고 확정**할 것.

---

## 6. 태스크

각 태스크: **목표 / 대상 파일 / 선행 / 구현 지침 / 완료 기준 / 프롬프트 예시 / 주의**.

### ── Phase A · 서버 격리·기반 (앱 없이 지금 적용) ──

#### TASK-M01 — 엔카 원자료 데이터 계층 격리(화이트리스트)  ✅ 완료(2026-09-06, 커밋 0fe3b56)
> 결정: median(소매 시세) **유지**('소매 시세' 라벨). 구현: `service.public_view()` + Jinja finalize(None→''). 함정으로 **HTML 주석(`<!-- 엔카 -->`)이 뷰소스로 새던 것** 발견·수정 → '화면 숨김이 아니라 데이터에서' 원칙의 실증.
- **목표**: 비관리자에게 나가는 물건 데이터에서 PRIVATE 필드를 **템플릿이 아니라 데이터 계층**에서 제거. 뷰소스·향후 JSON API 어디로도 안 샘.
- **대상**: `web/service.py`(또는 신규 `web/exposure.py`), `web/app.py`(상세·목록·리포트 라우트), 필요 시 템플릿의 median 참조.
- **선행**: 없음(가장 먼저).
- **구현 지침**:
  1. 착수 시 `PRAGMA table_info(vehicles)`로 실제 컬럼 확인 → §2 목록을 실제에 맞게 보정.
  2. 중앙 상수 `PRIVATE_FIELDS`(set)와 `public_view(v: dict, is_admin: bool) -> dict` 함수 신설: 관리자가 아니면 PRIVATE 키를 **삭제**(None으로 두지 말고 pop). BORDERLINE은 §5 결정에 따라 옵션 처리(기본: median은 `retail_price` 별칭으로만 남기고 원 키 제거 검토 — 우선은 유지하되 상수로 토글 가능하게).
  3. 상세/목록/리포트 라우트에서 템플릿에 넘기기 직전 `v = public_view(v, is_admin(request))` 적용. (관리자는 원본 그대로.)
  4. 기존 `{% if is_admin %}` 템플릿 가드는 **유지**(2차 방어). 단 데이터가 애초에 없으므로 비관리자 HTML엔 엔카 값이 존재하지 않아야 한다.
- **완료 기준**:
  - 비관리자 상세/목록/리포트 HTML(뷰소스)에 `comps`, `kcar_`, `encar_total`, `mean_price`, `market_cv`, `cross_source` 문자열/값이 **0건**.
  - 관리자(쿠키)로는 모두 표시.
  - `python -m pytest -q` 통과, 사용자 화면에 예상낙찰가·판정·신뢰도·추천전략은 그대로.
- **프롬프트 예시**: `docs/MONETIZATION_SPEC.md 의 TASK-M01만 구현해. 먼저 PRAGMA table_info(vehicles)로 실제 컬럼을 확인해 PRIVATE_FIELDS를 확정하고, public_view()를 만들어 비관리자 응답에서 엔카 원자료를 데이터 계층에서 제거해. 완료 기준의 grep 검증까지 보여줘.`
- **주의**: median_price를 완전 제거하면 '소매 차익' 섹션·재판매 손익분기가 깨진다 → §5 결정 먼저. 우선은 median 유지 + 나머지 PRIVATE만 제거로 시작.

#### TASK-M02 — 유출 테스트(회귀 방어)  ✅ 완료(2026-09-06, 커밋 0fe3b56)
> `tests/test_exposure.py`: public_view 단위 + 비관리자/관리자 렌더 유출 회귀(총 105 테스트 통과).
- **목표**: M01 이후 "비관리자 응답에 엔카 원자료가 절대 안 나온다"를 **자동 테스트**로 고정. 이후 어떤 라우트를 추가해도 이 테스트가 지킨다.
- **대상**: `tests/test_exposure.py`(신규). `conftest.py`의 임시 DB 패턴(`monkeypatch.setattr(db,'DB_PATH',tmp)`) 활용 — `tests/test_disappear.py` 참고.
- **구현 지침**: 임시 DB에 엔카 필드가 채워진 샘플 물건 삽입 → TestClient로 `/vehicle/{id}`, `/vehicles`, `/vehicle/{id}/report`를 **비관리자/관리자** 각각 호출 → 비관리자 응답 텍스트에 PRIVATE 값(예: 특정 comps 가격, kcar_median 숫자)이 **없음**을, 관리자엔 **있음**을 assert.
- **완료 기준**: 새 테스트가 M01 적용 상태에서 통과하고, M01을 되돌리면(임시로) 실패함을 확인.
- **주의**: `NAECHAGET_ADMIN_KEY`를 테스트 env로 세팅 후 `_admin_token()`으로 관리자 쿠키 생성(`web/app.py` 참고).

#### TASK-M03 — 관리자 접근 분리 + 서버단 보호  ✅ 완료(2026-09-06, 커밋 05662c3)
> 결정: **SSH 터널 전용**(서브도메인 미개설). `is_admin = XFF 없음 + Host loopback`(uvicorn
> 127.0.0.1:8000 전용 + 8000 외부차단이 근거). 공개 도메인의 /admin?key= 제거, 운영 라우트
> 비관리자 404, 관리자는 폰 프레임 생략. 접속: `ssh -L 9000:127.0.0.1:8000 …` → http://127.0.0.1:9000.
> 아래 원안(서브도메인)은 참고용으로 남김.
- **목표**: 관리자 화면·운영 라우트를 `admin.naechaget.co.kr`로 옮기고 사용자 도메인에서는 진입 자체를 차단. 앱/사용자 도메인엔 관리자 흔적 0.
- **대상**: nginx 설정(VM), `web/app.py`(호스트 기반 가드), 가비아 DNS.
- **구현 지침**:
  1. 가비아 DNS: `admin` A레코드 → 43.202.126.180 추가.
  2. certbot에 `admin.naechaget.co.kr` SAN 확장(`sudo certbot --nginx -d naechaget.co.kr -d www... -d admin.naechaget.co.kr`).
  3. nginx: `admin.` server 블록에 **IP allow/deny**(자택 고정 IP) 또는 **HTTP Basic**(`auth_basic`) 프론트. 자택이 유동 IP면 §7.3 SSH 터널 방식.
  4. `web/app.py`: 운영 라우트(`/run,/reanalyze,/results/run-now,/recompute-all,/daily/*,/vehicle/*/analyze|recompute|crosscheck|actual`)와 관리자 화면(엔카 카드 등)은 **`request` 호스트가 admin 서브도메인일 때만** 동작. 사용자 호스트로 오면 404. (기존 `is_admin` 키 게이트는 admin 서브도메인 내 2차 보호로 유지.)
- **완료 기준**: `curl https://naechaget.co.kr/run`(POST) → 404; `admin.` 호스트 + 허용 IP → 정상. 사용자 도메인 어디에도 `/admin` 링크·엔카 없음.
- **주의**: 지금은 `is_admin` 쿠키가 메인 도메인에 걸려 있다 — M03에서 관리자 판정을 **호스트 + 보호**로 이관하고 메인 도메인 쿠키 경로는 제거/무효화.

#### TASK-M04 — 사용자·등급 스캐폴딩(기능 배분 없이 뼈대만)  ✅ 완료(2026-09-06, 커밋 05662c3)
> `users`/`purchases`/`usage_daily` 테이블 + `db.get_user/upsert_user/set_user_tier` +
> `web/auth.py`(current_user/user_tier/require_tier). 전원 tier=1, 게이팅 미적용(M11+). Phase A 완료.
- **목표**: `users`/`purchases`/`usage_daily` 테이블 + `current_user(request)` + `require_tier(n)` 헬퍼. **이 단계에선 전원 무료(tier=1)** — 게이팅 로직만 심고 실제 제한은 M11+에서.
- **대상**: `web/db.py`(스키마·마이그레이션), `web/auth.py`(신규, 우선 스텁), `web/app.py`.
- **구현 지침**: §4 테이블 추가. `current_user`는 M05 전까지 익명(tier=1) 반환하는 스텁. `require_tier(n)`는 등급 부족 시 402/업그레이드 안내를 반환하되 지금은 어디에도 적용 안 함(정의만).
- **완료 기준**: 마이그레이션이 기존 DB에서 무손실 실행, 앱 정상 기동, 테스트 통과.

### ── Phase B · 인증 (앱 필요) ──

#### TASK-M05 — Google Sign-In 토큰 검증(서버)
- **목표**: 앱이 보낸 Firebase/Google ID 토큰을 서버가 검증해 `users` upsert하고 세션(httponly 쿠키 or Bearer) 발급.
- **대상**: `web/auth.py`, `requirements.txt`(`google-auth`), `web/app.py`(`POST /auth/google`).
- **구현 지침**: `google.oauth2.id_token.verify_oauth2_token`으로 aud=Firebase 프로젝트 검증 → `sub`→users.id. 성공 시 세션 쿠키(SameSite=Lax, Secure, httponly) 발급. 시크릿(Firebase 프로젝트 설정)은 **env**로.
- **완료 기준**: 유효 토큰 → 200 + 사용자 생성; 위조/만료 토큰 → 401. 단위 테스트(검증 함수 모킹).
- **주의**: 자체 비밀번호 저장 절대 금지(원칙 5).

#### TASK-M06 — 로그인 화면 + current_user 연결
- **목표**: 별도 로그인 화면(구글 버튼 1개) + `current_user(request)`가 실제 세션에서 사용자·등급 조회. 비로그인도 1단계로 열람 가능(로그인 강제는 결제 시점부터).
- **대상**: `web/templates/login.html`(신규), `web/auth.py`, `web/app.py`.
- **완료 기준**: 로그인 전/후 상태가 헤더에 반영, 등급이 DB에서 조회됨.

### ── Phase C · 결제 (앱 필요) ──

#### TASK-M07 — 앱: Google Play Billing 구독 결제
- **목표**: 앱에서 구독 상품 구매 플로우 → 구매 토큰 획득 → 서버 `POST /billing/verify`로 전송.
- **대상**: 안드로이드 앱 코드(TWA면 **네이티브 결제 브릿지 필요** — TWA 순수 웹뷰는 Billing 직접 못 씀 → §7.5 참고), Play Console 구독 상품 등록.
- **완료 기준**: 테스트 구독 구매 → 서버가 토큰 수신.
- **주의**: **TWA 한계** — 순수 TWA는 Play Billing API에 접근 못 한다. PWABuilder의 **Play Billing 옵션**(Digital Goods API + `com.android.vending.BILLING`) 또는 부분 네이티브가 필요. §7.5에서 결정.

#### TASK-M08 — 서버: 구매 검증 + acknowledge(3일 함정)
- **목표**: Play Developer API로 구매 토큰 검증 → `purchases` 기록 → **즉시 acknowledge** → `users.tier` 갱신.
- **대상**: `web/billing.py`(신규), `requirements.txt`(`google-api-python-client`), 서비스 계정 키(env/파일, git 제외).
- **구현 지침**: `purchases.subscriptionsv2.get`(또는 subscriptions.get)로 상태 확인 → 유효하면 tier 상향 + `sub_expiry`/`sub_state` 기록 → **`acknowledge` 호출**.
- **완료 기준**: 검증→acknowledge→tier 갱신이 멱등하게 동작(같은 토큰 재전송 안전). acknowledge 로그 확인.
- **⚠️ 함정(치명)**: **검증 후 3일 내 acknowledge 안 하면 구글이 자동 환불**한다 — 사용자는 결제했는데 돈 돌아가고 등급만 살아있는 상태. 검증 성공 즉시 acknowledge할 것.

#### TASK-M09 — RTDN 웹훅(해지·환불 실시간 반영)
- **목표**: 구독 해지·환불·갱신 등 **앱을 거치지 않는** 상태변화를 Pub/Sub RTDN으로 수신해 tier 자동 강등/유지.
- **대상**: `web/app.py`(`POST /billing/rtdn`), Google Cloud Pub/Sub 푸시 구독.
- **구현 지침**: RTDN 메시지의 `purchaseToken`으로 재검증 → `users`/`purchases` 갱신. 서명/출처 검증 필수.
- **완료 기준**: 테스트 해지 → 웹훅 수신 → `sub_state=canceled`, 만료 후 tier=1 강등.
- **⚠️ 함정**: 웹훅 없으면 **해지한 사용자가 계속 유료 기능 사용**. 만료 시각 기준 배치 강등도 병행(안전망).

#### TASK-M10 — 등급 만료 배치 + 서버 권위 최종화
- **목표**: `sub_expiry` 지난 사용자를 매일 tier=1로 강등하는 배치(기존 스케줄러에 훅). 모든 등급 판정은 서버 DB만 신뢰.
- **완료 기준**: 만료 사용자 자동 강등, 앱이 주장하는 등급 무시.

### ── Phase D · 페이월·기능 배분 ──

#### TASK-M11 — 무료 일일 열람 제한
- **목표**: 1단계 사용자 예상낙찰가 열람 **일 3건**(§5). `usage_daily` 카운트 → 초과 시 업그레이드/보상형 광고 안내.
- **대상**: `web/app.py`(상세 라우트), `web/auth.py`.
- **완료 기준**: 4번째 열람 시 페이월. 관리자·유료는 무제한.

#### TASK-M12 — 등급별 기능 게이팅
- **목표**: §5 매트릭스대로 D-3 알림/관심 무제한/전략밴드 전체/리포트 V2를 `require_tier`로 보호(서버·UI 양쪽).
- **완료 기준**: 각 기능이 등급 미달 시 서버에서 차단 + 업그레이드 CTA.

#### TASK-M13 — 보상형 광고 언락
- **목표**: "광고 시청 → 리포트/예상낙찰가 1건 해제". AdMob 보상형 + 서버 검증(SSV, Server-Side Verification)로 부정 방지.
- **대상**: 앱(AdMob 보상형), `web/app.py`(`/reward/verify`).
- **완료 기준**: 광고 완료 콜백 검증 후에만 1건 해제. 위조 콜백 거부.

#### TASK-M14 — 가격·상품 확정 + 개인정보처리방침/광고 신고
- **목표**: 구독/건당 상품 가격 확정(§5 임의값 교체), `/privacy` 개인정보처리방침(광고 SDK 식별자 수집 명시), Play 데이터 안전 섹션 신고, iOS면 ATT.
- **완료 기준**: Play 등록정보·데이터안전·개인정보 URL 일관.

---

## 7. 함정·운영 메모

1. **acknowledge 3일**(M08): 검증 즉시 acknowledge. 안 하면 자동 환불.
2. **RTDN 필수**(M09): 해지/환불은 앱 밖에서 발생. 웹훅 없으면 유료 기능 계속 사용됨. 만료 배치(M10) 병행.
3. **PUBLIC/PRIVATE는 PRAGMA로 검증**(M01): 문서의 필드 목록은 추정. `PRAGMA table_info(vehicles)`로 실제 확인 후 확정.
4. **관리자 IP**(M03): 자택이 유동 IP면 admin 서브도메인 IP allow 대신 **SSH 로컬 터널** 사용 —
   ```
   ssh -i ~/Downloads/naechaget.pem -L 9000:127.0.0.1:8000 ubuntu@43.202.126.180
   # 브라우저 http://127.0.0.1:9000 로 관리자 접근(외부 비노출). 이 경우 admin 서브도메인 자체를 안 열어도 됨.
   ```
5. **TWA + Billing 한계**(M07): 순수 TWA 웹뷰는 Play Billing 직접 호출 불가. 선택지 — (a) PWABuilder의 Play Billing/Digital Goods 옵션으로 재패키징, (b) 결제 화면만 부분 네이티브. Phase C 착수 전 결정.
6. **시크릿 관리**: Firebase 설정·Play 서비스계정 키·`NAECHAGET_ADMIN_KEY`는 전부 **env / VM 파일**(git 제외, `.gitignore` 확인). 코드·문서에 값 하드코딩 금지(설계서 C.4-4).
7. **엔카 준법**(원칙 1): 격리는 필요조건. 유료 가치는 자체 자산으로. 상업화 확대 전 수집 근거·이용조건 1회 정리 권장.

---

## 8. 착수 전 운영자가 결정할 것

- [ ] **무료/유료 경계**(§5 매트릭스) 확정 — 각 단계 기능·가격.
- [ ] **median(소매 시세) 노출 정책**(§2 BORDERLINE) — 유지(라벨 '소매 시세') vs 제거 후 소매차익 관리자화.
- [ ] **관리자 접근 방식**(§7.4) — admin 서브도메인 IP allow vs SSH 터널(유동 IP면 후자).
- [ ] **TWA 결제 방식**(§7.5) — PWABuilder Play Billing 재패키징 vs 부분 네이티브.
- [ ] **Firebase 프로젝트/AdMob 계정** 생성 여부.

> 각 결정이 서면 관련 태스크의 "구현 지침"을 그 결정에 맞게 1줄 수정한 뒤 Claude Code에 전달.
