<!-- 자동 생성: appstore-setup-guide 워크플로(2026-09-06 리서치·합성). 콘솔 UI는 변동될 수 있으니 현장에서 재확인. -->

# 경매로 내차GET — 스토어 출시·수익화 단일 실행 체크리스트

> 대상 앱: TWA(PWABuilder 래퍼) · 패키지 `kr.co.naechaget.twa` · 도메인 `https://naechaget.co.kr`
> 원칙: 웹=앱(웹 수정은 재심사 불필요, 패키지 설정 변경만 재빌드). 순서·의존성 반드시 지킬 것.

---

## 0. 이미 완료된 것 (재확인만)

- [x] PWA 준비 완료 (manifest·서비스워커·아이콘 192/512/maskable·theme #0b142b)
- [x] 개인정보처리방침 게시: `https://naechaget.co.kr/privacy`
- [x] `/.well-known/assetlinks.json` 서빙 중 — **단, `sha256_cert_fingerprints`가 PLACEHOLDER (미기입)**
- [x] `assetlinks.json`의 `package_name`이 `kr.co.naechaget.twa`로 반영됨

> ⚠️ **도메인 불일치 확인 필요(불확실)**: 리서치 일부는 PWABuilder 입력값으로 `naechaget.duckdns.org`를, 다른 곳은 `naechaget.co.kr`을 씁니다. **TWA의 startUrl 도메인과 assetlinks 서빙 도메인은 반드시 동일**해야 하므로, 실제 canonical 도메인 하나(권장: 소유 도메인 `naechaget.co.kr`)로 통일하고 PWABuilder에도 그 주소를 입력하세요. 리다이렉트가 있으면 "리다이렉트 도착지" 주소를 넣어야 합니다.

---

## 1. Google Play 개발자 계정 등록 — **가장 먼저 시작** (본인확인에 며칠 소요)

**운영자가 할 일 (콘솔):**
- [ ] `play.google.com/console` 로그인 → 등록비 **$25(1회)** 결제
- [ ] 계정 유형 **Personal(개인)** 선택 — 사업자등록/D-U-N-S 불필요(개인 가능)
- [ ] 실명·주소·전화·이메일로 본인확인(신분증 요구될 수 있음) 완료

**클로드 코드/서버:** (없음)

> 본인확인 심사가 병목이 될 수 있어 **다른 작업과 병행**하되 이 단계를 제일 먼저 착수.

---

## 2. PWABuilder로 .aab 패키징

**운영자가 할 일 (PWABuilder 웹):**
- [ ] `pwabuilder.com`에 canonical HTTPS 주소 입력 → 리포트 실행 → **Package For Stores → Android → Google Play**
- [ ] Package ID = `kr.co.naechaget.twa` 확인 (**출시 후 영구 변경 불가**)
- [ ] App name `경매로 내차GET` / Launcher `내차GET` / startUrl `/?src=twa` / theme·background 자동 채움 확인
- [ ] Version code=1, Version name=1.0.0 확인
- [ ] Signing key = **New** 선택 (alias `naechaget` + 비밀번호 설정) — 이것이 당신의 **"업로드 키"**
  - None은 AAB 미생성 버그로 비권장 / Mine은 향후 "업데이트"용
- [ ] Generate → zip 다운로드 → 압축 해제:
  - `app-release-signed.aab` (Play 업로드용)
  - `signing.keystore` + `signing-key-info.txt` (업로드 키·SHA-256 지문) → **오프라인 안전 백업 필수**

**클로드 코드/서버:** (없음 — 순수 콘솔 작업)

> ⚠️ `signing.keystore` 분실 시 같은 업로드 정체성으로 업데이트 불가(Google에 재설정 요청은 가능하나 번거로움).
> ⚠️ (선택) Play 결제를 넣을 거면 이 단계에서 **Play Billing 토글 ON** 후 빌드 (자세히는 §8).

---

## 3. Play Console에 앱 생성 + 내부 테스트 업로드

**운영자가 할 일 (콘솔):**
- [ ] 앱 만들기: 이름 `경매로 내차GET`, 기본 언어 한국어, App, Free, 선언 체크
- [ ] **테스트 및 배포 → 테스트 → 내부 테스트(Internal testing) → 새 버전 만들기 → `.aab` 업로드**
- [ ] 첫 업로드 시 **Play App Signing 자동 활성화**(기본값) 확인 → 출시 노트 입력 → 내부 테스트 출시

**클로드 코드/서버:** (없음)

> 내부 테스트는 개인계정의 "테스터 12명·14일" 요건 **예외** → 바로 출시 가능. 스토어 등록정보 미완성이어도 롤아웃됨.
> ⚠️ 업로드한 `.aab`는 "업로드 키"로 서명된 것 — **이 지문은 assetlinks에 넣을 값이 아님**(다음 단계 참조).

---

## 4. 앱 서명 키 SHA-256 확보 — **★ TWA 성패의 핵심 ★**

**운영자가 할 일 (콘솔):**
- [ ] **테스트 및 배포 → 앱 무결성(App integrity) → 앱 서명(App signing)** 페이지 열기
- [ ] 두 인증서 중 **"앱 서명 키 인증서(App signing key certificate)"의 SHA-256**을 복사
  - ❌ "업로드 키 인증서" SHA-256이 아님 / ❌ PWABuilder가 준 지문이 아님
- [ ] (권장) `signing-key-info.txt`의 **업로드 키 SHA-256**도 함께 확보 (로컬 APK 테스트용, 배열에 같이 넣으면 안전)

**클로드 코드/서버:** (없음 — 값 확보만. 기입은 §5)

> 이 페이지는 **첫 .aab 업로드 후에만 생성**됨 → 그래서 순서가 "업로드 → 지문 확보 → assetlinks 교체"로 고정(역순 불가).
> **TWA 실패 1위 원인**: assetlinks에 업로드 키/ PWABuilder 지문을 넣는 것. Play가 사용자 배포본을 자기 "앱 서명 키"로 재서명하므로, 실제 기기에서 검증되는 건 이 값.

---

## 5. assetlinks.json에 SHA-256 기입 — **▶ 클로드 코드에게 맡길 것**

**운영자가 할 일:**
- [ ] §4에서 복사한 **앱 서명 키 SHA-256**(콜론 포함 대문자 HEX)을 클로드 코드에 전달
- [ ] (권장) 업로드 키 SHA-256도 함께 전달

**클로드 코드/서버가 할 일:**
- [ ] `web/static/.well-known/assetlinks.json`의 `PLACEHOLDER...` 자리를 실제 지문으로 교체
  - `sha256_cert_fingerprints`에 **앱 서명 키 + 업로드 키 두 값 배열**로 기입(가장 안전)
  - `package_name` = `kr.co.naechaget.twa` 정확히 유지
- [ ] EC2 재배포: `ubuntu@43.202.126.180`, `/home/ubuntu/app`에서 `git pull` + 서비스 재시작
- [ ] `https://naechaget.co.kr/.well-known/assetlinks.json`이 **HTTPS·리다이렉트 없이·유효 JSON**으로 열리는지 확인 (Google Digital Asset Links API 테스터로 검증)

---

## 6. TWA 검증 테스트

**운영자가 할 일 (실기기):**
- [ ] 내부 테스트 링크로 설치 → 실행 → **상단 브라우저 URL바가 안 뜨면 검증 성공**
- [ ] URL바가 뜨면 = 지문 오류 → §4 값(앱 서명 키)으로 교체 후 재배포·재검증

**클로드 코드/서버:** (필요 시 재배포)

---

## 7. 스토어 콘텐츠 & 데이터 안전 신고

**운영자가 할 일 (콘솔):**
- [ ] 정책 → 앱 콘텐츠 → **개인정보처리방침 URL** = `https://naechaget.co.kr/privacy`
- [ ] **데이터 안전(Data safety)** 작성:
  - 현재(로그인·결제·광고 없음, 공개 조회) → "개인정보 수집 없음 / 광고 ID 수집 안 함"으로 신고 가능
  - HTTPS → "전송 중 암호화됨" + "삭제 요청 방법" 채우기
  - ⚠️ **유료화(로그인) 착수 시 "이메일 주소" 수집 추가 신고 / 광고(AdSense·애널리틱스) 도입 시 광고ID·기기식별자 신고 + AD_ID 권한 선언** — 반드시 갱신
- [ ] 앱 액세스(로그인 없음 → 특별 접근 불필요), 광고(현재 없음), 콘텐츠 등급 설문, 대상 연령, 정부앱 여부
- [ ] 스토어 등록정보: 아이콘 512×512, 피처 그래픽 1024×500, **실제 앱 스크린샷**, 짧은 설명(80자)·긴 설명(4000자)
  - "단순 웹뷰" 반려 방지: **"경매 분석/입찰가 산정" 등 앱 고유 가치**를 설명에 명확히 기술

**클로드 코드/서버:** (없음)

> ⚠️ 데이터 안전 신고가 실제 동작·개인정보처리방침과 어긋나면 대표적 거부 사유. TWA라도 **웹에서 수집하는 데이터까지 신고 책임**이 개발자에게 있음.

---

## 8. 프로덕션 승격 (준비되면)

**운영자가 할 일 (콘솔):**
- [ ] 신규 개인계정 요건: **테스터 12명 이상 · 14일 연속 비공개 테스트** 통과 후 Production 승격
  - 일정 계획에 이 14일을 반드시 포함
- [ ] targetSdk 요건: 최신 API(2026 기준 API 35/Android 15 이상) — 최신 PWABuilder로 빌드하면 자동 충족(오래된 캐시 버전 사용 금지)

---

## TWA 제약에 따른 기능별 권고 (정직하게)

### 로그인 → **웹 OAuth (GIS 직결) 권장**
- TWA는 실제 Chrome(Custom Tabs)이라 웹 OAuth가 정상 동작(네이티브 SDK 불필요, `disallowed_useragent` 대상 아님).
- **Google Identity Services 토큰 콜백 방식**(페이지 이탈·팝업 없음)이 가장 안정적. 리다이렉트/팝업은 불안정.
- **운영자:** Google Cloud Console에서 OAuth 동의화면(External, In production 게시, 스코프 `openid/email/profile`만) + **"웹 애플리케이션" 유형** 클라이언트 ID 생성(승인 JS 원본 `https://naechaget.co.kr`). ❌ 안드로이드 유형 ID 쓰면 aud 불일치로 실패.
- **클로드 코드/서버:** `web/auth.py`에 `verify_oauth2_token(token, ..., WEB_CLIENT_ID)` 검증 → sub/email로 세션 쿠키(Secure+HttpOnly+SameSite=Lax) 발급. **등급/유료 여부는 서버 DB에서만 판정**(클라이언트 값 신뢰 금지).
- Firebase도 가능하나 `signInWithRedirect` 서드파티 스토리지 문제·별도 토큰 검증(Admin SDK `verify_id_token`) 등 함정이 더 많아 **이 케이스엔 GIS 직결 권장**.

### 광고 → **AdSense(웹) 권장, AdMob 불가**
- **순수 TWA에 AdMob(배너·전면·보상형) 표시 불가** — 네이티브 표면이 없고 Google도 공식 미지원(android-browser-helper #535). 웹에 AdMob 코드 주입은 정책 위반.
- **AdSense**는 실제 Chrome이 실제 사이트를 렌더링하므로 정상 노출.
  - **클로드/서버:** `base.html` `<head>`에 AdSense 스니펫 삽입 + `/ads.txt` 라우트(`google.com, pub-XXXX, DIRECT, f08c47fec0942fa0`) 게시. (❌ `app-ads.txt`는 AdMob용, 불필요)
  - **운영자:** AdSense에 `naechaget.co.kr` 등록·심사(수일~수주), 결제 프로필(한국 개인·PIN 우편·은행계좌·세금정보) 등록, EEA/UK 트래픽 있으면 인증 CMP 설정.
  - ⚠️ **보상형(rewarded)은 AdSense에 없음**(Ad Manager 전용, 무거움) → 프리미엄 잠금 해제는 **구독**으로 설계 권장.
  - AdMob이 정말 필요하면 TWA를 버리고 **Capacitor/Cordova 하이브리드 재구축** 필요(초기 비권장).

### 결제/구독 → **Play Billing (Digital Goods API) 또는 웹 PG**
- 앱 내 디지털 구독/리포트 판매 시 **원칙상 Google Play 결제**(수수료 15~30%). 한국은 인앱결제법상 제3자 결제 여지 있으나 **정책 확인 필요(불확실)**.
- TWA에서 Play 결제 = **Digital Goods API + Payment Request(`https://play.google.com/billing`)** + **Play Billing Library 7**(2025-08-31 강제) 필요. PWABuilder에서 `features.playBilling.enabled=true` + `alphaDependencies.enabled=true` 토글 후 재빌드.
- ⚠️ Play 결제는 **브라우저에서 unsupported context 오류** → Play 트랙 설치 앱 안에서만 동작/테스트 가능. SKU는 Play Console에 별도 등록 + 웹 코드 구현 선행 필요.
- 웹 PG(토스페이먼츠 등)는 구현이 단순하나 앱 내 디지털재 판매엔 정책 검토 필요.

---

## 운영자가 준비할 값 목록

| 값 | 내용 | 확보 시점 |
|---|---|---|
| 패키지명(영구) | `kr.co.naechaget.twa` | 이미 확정 |
| Canonical 도메인 | `https://naechaget.co.kr` (통일 필요) | 지금 |
| 서명키 alias/비번 | alias `naechaget` + keystore·키 비밀번호 | §2 (New 생성 시) |
| **앱 서명 키 SHA-256** | Play Console → 앱 무결성 → 앱 서명 | **§4 (첫 .aab 업로드 후)** |
| 업로드 키 SHA-256(권장) | `signing-key-info.txt` | §2 |
| Play 개발자 계정 | $25(1회) + 결제수단 + 본인확인 | §1 |
| OAuth 웹 클라이언트 ID | 프런트 `data-client_id` = 백엔드 검증 aud 동일 | 로그인 도입 시 |
| AdSense pub-ID | `pub-XXXXXXXXXXXXXXXX` | 광고 도입 시 |
| 스토어 자산 | 아이콘 512×512·피처 1024×500·스크린샷·설명 | §7 |
| 결제 프로필(AdSense) | 실명·주소(PIN)·은행계좌·세금정보 | 광고 수익화 시 |

---

## 마지막 — 함정 정리 (반드시 숙지)

- **[신원확인 지연]** 개인계정 본인확인에 며칠 소요 → **§1을 제일 먼저**.
- **[assetlinks 지문 오류]** 업로드 키/PWABuilder 지문 넣으면 URL바 노출·"그냥 웹사이트"로 반려. **반드시 Play 앱 서명 키 SHA-256** (두 값 배열 권장).
- **[순서 고정]** 앱 서명 SHA-256은 첫 .aab 업로드 후에만 생성 → 역순 불가.
- **[프로덕션 14일]** 신규 개인계정은 프로덕션 전 테스터 12명·14일 비공개 테스트 필수(내부 테스트는 예외). 일정에 반영.
- **[자기 클릭 금지]** AdSense는 테스트 광고가 없음 — 본인 클릭·본인 트래픽 = 무효 트래픽 = **계정 영구 정지**. 배치 확인은 다른 기기에서 "보기만".
- **[데이터 안전 일치]** 신고 내용이 실제 동작·개인정보처리방침과 어긋나면 거부. 로그인·광고 도입 시 **반드시 갱신**.
- **[버전코드 +1]** 재업로드마다 appVersionCode 증가 필수(안 하면 거부).
- **[재빌드 서명 일관성]** 이후 재빌드 시 반드시 **Mine**으로 같은 `signing.keystore` 사용(새 키는 업로드 거부).
- **[keystore 백업]** `signing.keystore` + `signing-key-info.txt` 오프라인 백업. 분실 시 업데이트 불가.
- **[IP 리스크]** SK엔카·케이카 원자료 노출은 저작권 민원 소지 → 배포본에 관리자 계층 데이터가 안 나오는지(public_view) 재확인.
- **[웹=앱]** 웹 수정은 재심사 불필요. 단 패키지 설정(이름·아이콘·버전·Play Billing 토글) 변경은 재빌드+재업로드 필요.

**불확실 표기:** 한국 인앱결제 제3자 결제 허용 범위, 도메인(duckdns vs co.kr) 최종 통일값, targetSdk 정확 버전은 실제 콘솔·최신 정책에서 확인 요망.
