# 안드로이드 앱 빌드 가이드 (TWA — 웹앱 그대로 앱화)

## 방침 (신뢰성 우선)
경쟁앱 '법차' 리뷰의 최다 불만은 **로그인 오류·실행 안 됨**이다. 그래서 앱을 **처음부터 네이티브로
다시 만들지 않고**, 이미 검증된 **웹앱(PWA)을 그대로 감싸는 TWA(Trusted Web Activity)** 로 만든다.

- ✅ **웹 = 앱**: 화면·로직·데이터가 웹과 100% 동일 → 앱에서만 나는 버그·불일치가 원천적으로 없음.
- ✅ 우리 앱은 **로그인이 없어**(공개 조회) 경쟁앱의 로그인 오류 부류가 아예 발생하지 않음.
- ✅ 웹을 고치면 앱도 즉시 반영(스토어 재심사 불필요, 콘텐츠는 서버가 제공).
- ✅ 웹 URL은 그대로 유지(요청사항 충족). 앱은 그 URL을 전체화면으로 띄우는 얇은 껍데기.

## 완료된 것 (이 저장소)
- **PWA**: `web/static/manifest.webmanifest`, 서비스워커 `/sw.js`, 앱아이콘(`web/static/icons/`), 오프라인 페이지.
  → 지금도 **모바일 브라우저에서 "홈 화면에 추가"** 하면 standalone 앱으로 실행됨(아이콘 "경매로 내차GET").
- **Digital Asset Links** 라우트: `/.well-known/assetlinks.json` (지문만 넣으면 URL바 없는 신뢰앱 검증).
- **TWA 설정 템플릿**: `android/twa-manifest.json`.

## 전제조건 (중요)
- **고정 HTTPS 도메인**이 필요하다. 지금의 임시 터널 주소(trycloudflare)는 매번 바뀌므로 **플레이스토어 앱에는 못 씀**.
  → 먼저 상시 호스팅 + 도메인을 정한다(예: `naechaget.kr`). 배포는 [DEPLOY.md](DEPLOY.md).
- 구글 플레이 개발자 계정($25 1회).

## 빌드 방법 A — PWABuilder (가장 쉬움, 빌드도구 불필요·권장)
1. 웹을 고정 도메인에 배포(HTTPS).
2. https://www.pwabuilder.com 접속 → 도메인 입력 → **Android** 패키지 생성.
3. 다운로드된 **서명된 `.aab`** 를 구글 플레이 콘솔에 업로드.
4. PWABuilder가 알려주는 **SHA-256 지문**을 `web/static/.well-known/assetlinks.json` 의
   `PLACEHOLDER...` 자리에 넣고 재배포 → URL바 없는 신뢰앱으로 검증됨.
   (플레이 앱서명 사용 시, 플레이 콘솔 → 앱 무결성의 지문을 넣어야 함)

## 빌드 방법 B — Bubblewrap CLI (직접 빌드, Java+Android SDK 필요)
> 이 개발 환경엔 Java·Android SDK가 없어 여기서는 빌드 불가. 아래는 갖춰진 PC 기준.
```bash
npm i -g @bubblewrap/cli
# android/twa-manifest.json 의 host/도메인 먼저 실제값으로 교체
bubblewrap init --manifest https://<도메인>/static/manifest.webmanifest
bubblewrap build          # app-release-signed.aab + assetlinks 지문 출력
```
출력된 지문을 `assetlinks.json`에 반영 후 재배포.

## 패키지 정보(제안)
- packageId: `kr.co.naechaget.twa` (원하는 값으로 변경 가능, 스토어와 일치해야 함)
- 앱 이름: **경매로 내차GET** / 런처: **내차GET**
- 색상: theme `#ffffff`, splash/네비 다크 `#0b142b`, 포인트 `#f3b63e`
- 아이콘: `web/static/icons/icon-512.png`(any) · `icon-maskable-512.png`(maskable)

## 유료화 참고
- 현재 앱은 로그인·결제가 없다(공개 조회). 유료(회원·건당 리포트)는 준법 정리(개인정보·전자상거래 표시의무·
  엔카/케이카 상용노출) 후 활성화 — [compliance-review.md](compliance-review.md), MON-01/02 참조.
